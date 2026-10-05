"""
ModalAdapter: one Modal account (workspace) as an engine (spec 0003, 4.11).

Built per engine, in worker-remote only, with that engine's credentials opened
from the sealed blob - they live in this object and in a per-account
`modal.Client.from_credentials(...)`, never in the process environment, and are
registered for log redaction. Subprocesses (billing report, deploy) get an
environment built from scratch with the token as variables, never in argv.

    test_connection()   auth + workspace + is the app deployed; no container, no GPU
    ensure_ready()      compares the recorded deploy with the expected fingerprint; no network
    execute()           spawn, persist the call id, wait in 15 s slices (heartbeat), cancel at
                        deadline_at; validate the output against protocol.py. With live
                        captions (ctx.on_segments) it waits in 3 s slices and drains the
                        attempt's partition of the live Queue between them (protocol 3)
    resume()            re-attach to a recorded call (worker-remote restarted)
    cancel()            the cooperative flag in the state Dict + FunctionCall.cancel()
    lookup_attempt()    attempt_key -> {container_id, call_id} written by the container
    classify_error()    provider exceptions -> ErrorCode (Appendix J)
    provider_spend()    `modal billing report --json`, parsed strictly: a missing field is an
                        error, never 0

`modal` is imported lazily: no other process ever loads it.
"""

import contextlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Mapping, Optional, Union

from shared.engines.redact import redact, register_secret
from workers.engines.base import EngineError, ErrorCode, ExecResult, ExecutionContext, HealthReport, Usage
from workers.engines.modal_apps import protocol

logger = logging.getLogger(__name__)

BILLING_TIMEOUT_SECONDS = 60
CREDENTIAL_FIELDS = ("token_id", "token_secret")


class BillingError(Exception):
    """The billing report could not be read or did not have the expected shape (fail closed)"""


# --- error classification (Appendix J) -------------------------------------------------------

_QUOTA = re.compile(r"spending limit|billing cycle|budget|workspace\b.*\bdisabled|is disabled|out of credit|"
                    r"payment (?:required|failed)|plan limit", re.I)
_AUTH = re.compile(r"invalid token|token .{0,40}(?:invalid|revoked|expired|not found)|unauthenticated|"
                   r"unauthori[sz]ed|authentication failed|bad credentials|token_id|token secret", re.I)
_NOT_DEPLOYED = re.compile(r"not found|no such app|has not been deployed|not deployed|does not exist", re.I)
_CAPACITY = re.compile(r"rate.?limit|too many requests|capacity|no (?:available )?gpus?|resource exhausted", re.I)
_TIMEOUT = re.compile(r"timed? ?out|deadline exceeded|timeout", re.I)
_TRANSIENT = re.compile(r"unavailable|connection (?:reset|refused|error|closed)|temporarily|try again", re.I)


def classify_error(exc: BaseException) -> str:
    if isinstance(exc, EngineError):
        return exc.code
    name = type(exc).__name__
    text = f"{name}: {exc}"
    if protocol.INPUT_REJECTED_PREFIX in text or name in ("InputRejected", "RequestSizeError"):
        return ErrorCode.INPUT_REJECTED
    if _QUOTA.search(text):
        return ErrorCode.QUOTA_EXHAUSTED
    if name in ("AuthError", "PermissionDeniedError") or _AUTH.search(text):
        return ErrorCode.AUTH
    if name == "OutputExpiredError":
        return ErrorCode.LOST
    if name == "FunctionTimeoutError":
        return ErrorCode.TIMEOUT
    if name == "NotFoundError" or (name in ("InvalidError", "ExecutionError") and _NOT_DEPLOYED.search(text)):
        return ErrorCode.NOT_DEPLOYED
    if name == "ResourceExhaustedError" or _CAPACITY.search(text):
        return ErrorCode.CAPACITY
    if name in ("ConnectionError", "ClientClosed", "ServiceError") or isinstance(exc, (ConnectionError, OSError)) \
            or _TRANSIENT.search(text):
        return ErrorCode.TRANSIENT
    if _TIMEOUT.search(text) and name not in ("RemoteError", "UserCodeException"):
        return ErrorCode.TIMEOUT
    return ErrorCode.INTERNAL


def _is_wait_timeout(exc: BaseException) -> bool:
    """FunctionCall.get(timeout=...) found no output yet (not the function's own timeout)"""
    name = type(exc).__name__
    if name in ("FunctionTimeoutError", "OutputExpiredError"):
        return False
    return isinstance(exc, TimeoutError) or name == "TimeoutError"


# --- billing ----------------------------------------------------------------------------------


def parse_billing_report(stdout: str) -> Decimal:
    """Sum of `cost` over `modal billing report --json` rows; anything unexpected raises BillingError"""
    try:
        rows = json.loads(stdout)
    except (TypeError, ValueError) as e:
        raise BillingError(f"the billing report is not JSON ({type(e).__name__})") from None
    if not isinstance(rows, list):
        raise BillingError("the billing report is not a list of rows")
    total = Decimal("0")
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or "cost" not in row:
            raise BillingError(f"billing row {i} has no `cost` field")
        try:
            cost = Decimal(str(row["cost"]))
        except (InvalidOperation, ValueError):
            raise BillingError(f"billing row {i} has a cost that is not a number") from None
        if not cost.is_finite() or cost < 0:
            raise BillingError(f"billing row {i} has an invalid cost")
        total += cost
    return total


def provider_env(token_id: str, token_secret: str, home: str, *, environment: Optional[str] = None,
                 extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """
    The whole environment of a provider subprocess, built from scratch (Appendix M):
    nothing of this process's environment leaks in except PATH and PYTHONPATH.
    """
    env = {
        "PATH": os.environ.get("PATH") or "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "HOME": home,
        "MODAL_TOKEN_ID": token_id,
        "MODAL_TOKEN_SECRET": token_secret,
    }
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    if environment:
        env["MODAL_ENVIRONMENT"] = environment
    env.update(extra or {})
    return env


class ModalAdapter:
    type_name = "modal"

    def __init__(self, engine: Mapping[str, Any], credentials: Mapping[str, str], *, modal_module=None,
                 clock: Callable[[], float] = time.time, run: Callable = subprocess.run):
        missing = [f for f in CREDENTIAL_FIELDS if not (credentials or {}).get(f)]
        if missing:
            raise EngineError(ErrorCode.AUTH, f"credentials lack {', '.join(missing)}")
        self.engine = dict(engine)
        self._token_id = credentials["token_id"]
        self._token_secret = credentials["token_secret"]
        register_secret(self._token_id)
        register_secret(self._token_secret)
        self._modal = modal_module
        self._client = None
        self._clock = clock
        self._run = run

    def __repr__(self):
        return f"ModalAdapter({self.engine.get('slug')!r})"  # never the credentials

    # --- provider handles ---------------------------------------------------------------------

    @property
    def modal(self):
        if self._modal is None:
            import modal  # only worker-remote and the deploy CLI get here
            self._modal = modal
        return self._modal

    @property
    def environment(self) -> Optional[str]:
        return (self.engine.get("config") or {}).get("modal_environment")

    def client(self):
        if self._client is None:
            self._client = self.modal.Client.from_credentials(self._token_id, self._token_secret)
        return self._client

    def _state(self):
        return self.modal.Dict.from_name(protocol.STATE_DICT, environment_name=self.environment,
                                         create_if_missing=True, client=self.client())

    def _live_queue(self):
        return self.modal.Queue.from_name(protocol.LIVE_QUEUE, environment_name=self.environment,
                                          create_if_missing=True, client=self.client())

    def _runner(self):
        cls = self.modal.Cls.from_name(protocol.APP_NAME, protocol.CLS_NAME, environment_name=self.environment,
                                       client=self.client())
        return cls()

    def _call(self, call_id: str):
        return self.modal.FunctionCall.from_id(call_id, client=self.client())

    # --- health -------------------------------------------------------------------------------

    def test_connection(self) -> HealthReport:
        """Credentials, workspace and deployment, without starting any container"""
        checked = datetime.utcnow().isoformat()
        try:
            state = self._state().hydrate(client=self.client())
        except Exception as e:
            return HealthReport(False, classify_error(e), redact(str(e))[:500], checked_at=checked)
        deployed, fingerprint = None, None
        try:
            self.modal.Function.from_name(protocol.APP_NAME, protocol.META_FUNCTION, environment_name=self.environment,
                                          client=self.client()).hydrate(client=self.client())
            deployed = True
            recorded = state.get(protocol.DEPLOYMENT_KEY) or {}
            fingerprint = recorded.get("fingerprint") if isinstance(recorded, dict) else None
        except Exception as e:
            code = classify_error(e)
            if code != ErrorCode.NOT_DEPLOYED:
                return HealthReport(False, code, redact(str(e))[:500], checked_at=checked)
            deployed = False
        detail = "credentials and workspace ok; " + ("app deployed" if deployed else "app not deployed yet")
        return HealthReport(True, None, detail, deployed=deployed, deployed_fingerprint=fingerprint, checked_at=checked)

    def ensure_ready(self, feature: str, expected_fingerprint: str) -> str:
        """ready | not_deployed | needs_redeploy | unhealthy - from the recorded deploy only (no network)"""
        recorded = (self.engine.get("deployments") or {}).get(feature) or {}
        if not recorded.get("fingerprint"):
            return "not_deployed"
        if recorded.get("protocol") != protocol.PROTOCOL_VERSION:
            return "unhealthy"
        if recorded["fingerprint"] != expected_fingerprint:
            return "needs_redeploy"
        return "ready"

    # --- execution ----------------------------------------------------------------------------

    def execute(self, *, media: Union[bytes, Callable[[], bytes]], suffix: str, options: Dict[str, Any], ctx: ExecutionContext,
                budget_seconds: float, max_media_bytes: int = protocol.MAX_MEDIA_BYTES,
                spawn_guard: Optional[Callable[[], Any]] = None) -> ExecResult:
        """
        Spawn one transcription and wait for it. The call id and the deadline are
        persisted (ctx.record_call_id) before the first wait, so a worker that dies
        here leaves a call the next one can resume or cancel. `media` may be a
        loader, called inside `spawn_guard` so only that many files sit in memory.
        """
        try:
            with (spawn_guard or contextlib.nullcontext)():  # the bytes travel with the spawn
                now = self._clock()
                request = protocol.build_request(attempt_key=ctx.attempt_key,
                                                 media=media() if callable(media) else media, suffix=suffix,
                                                 options=options, deadline_unix=now + budget_seconds,
                                                 max_media_bytes=max_media_bytes, live=ctx.on_segments is not None)
                call = self._runner().transcribe.spawn(request)
        except protocol.ProtocolError as e:
            raise EngineError(ErrorCode.INPUT_REJECTED, str(e)) from None
        except Exception as e:
            raise EngineError(classify_error(e), redact(str(e))[:500]) from None
        del request
        spawned_at = datetime.utcfromtimestamp(now)
        deadline_at = spawned_at + timedelta(seconds=budget_seconds)
        ctx.deadline_at = deadline_at
        ctx.record_call_id(call.object_id, spawned_at, deadline_at)
        return self._wait(call, call.object_id, ctx, spawned_at)

    def resume(self, call_id: str, ctx: ExecutionContext, spawned_at: datetime) -> ExecResult:
        """Re-attach to a call recorded by an earlier worker (its deadline still applies)"""
        try:
            call = self._call(call_id)
        except Exception as e:
            raise EngineError(classify_error(e), redact(str(e))[:500]) from None
        return self._wait(call, call_id, ctx, spawned_at)

    def _partial_usage(self, ctx: ExecutionContext, spawned_at: datetime) -> Usage:
        usage = Usage(measured_seconds=max((datetime.utcfromtimestamp(self._clock()) - spawned_at).total_seconds(), 0))
        entry = self.lookup_attempt(ctx.attempt_key)
        if entry:
            usage.container_id = str(entry.get("container_id") or "")[:protocol.MAX_ID_CHARS] or None
        return usage

    def drain_live(self, attempt_key: str, on_segments: Callable[[list], None], *, max_batches: int = 0) -> int:
        """
        Move what the container pushed for this attempt to `on_segments`, validated;
        returns the batches read. Best effort: live text is cosmetic, so a read
        error or a malformed batch is logged and skipped, never raised.
        """
        limit = max_batches or protocol.LIVE_DRAIN_MAX
        try:
            raw = self._live_queue().get_many(limit, block=False, partition=protocol.live_partition(attempt_key))
        except Exception as e:
            logger.debug(f"[ENGINES] Live captions of {attempt_key} unreadable: {redact(str(e))[:200]}")
            return 0
        segments = []
        for entry in raw or []:
            try:
                segments.extend(protocol.parse_live_batch(entry))
            except protocol.ProtocolError as e:
                logger.warning(f"[ENGINES] Dropped a malformed live batch of {attempt_key}: {e}")
        if segments:
            try:
                on_segments(segments)
            except Exception as e:
                logger.warning(f"[ENGINES] Could not record live captions of {attempt_key}: {e}")
        return len(raw or [])

    def clear_live(self, attempt_key: str) -> None:
        """Drop an attempt's partition once its result is in (its TTL would, later)"""
        try:
            self._live_queue().clear(partition=protocol.live_partition(attempt_key))
        except Exception as e:
            logger.debug(f"[ENGINES] Could not clear live captions of {attempt_key}: {redact(str(e))[:200]}")

    def _wait(self, call, call_id: str, ctx: ExecutionContext, spawned_at: datetime) -> ExecResult:
        live = ctx.on_segments is not None
        slice_seconds = min(ctx.live_poll_seconds, ctx.poll_seconds) if live else ctx.poll_seconds
        beat_at = self._clock()
        try:  # the partition is dropped once the attempt is over, never when this thread just dies
            while True:
                now = datetime.utcfromtimestamp(self._clock())
                remaining = (ctx.deadline_at - now).total_seconds() if ctx.deadline_at else slice_seconds
                if remaining <= 0:
                    self.cancel(call_id, ctx.attempt_key)
                    raise EngineError(ErrorCode.TIMEOUT, "deadline_at passed: the call was cancelled",
                                      self._partial_usage(ctx, spawned_at))
                try:
                    raw = call.get(timeout=max(min(slice_seconds, remaining), 0.01))
                    break
                except Exception as e:
                    if _is_wait_timeout(e):
                        if live:
                            self.drain_live(ctx.attempt_key, ctx.on_segments)
                        # With live captions the slices are short; the heartbeat keeps its cadence
                        if not live or self._clock() - beat_at >= ctx.poll_seconds - slice_seconds / 2:
                            beat_at = self._clock()
                            if not ctx.heartbeat():
                                logger.warning(f"[ENGINES] Usage {ctx.usage_id} is no longer ours; still waiting "
                                               f"for the call so its output is not lost")
                            if ctx.on_progress:
                                ctx.on_progress((now - spawned_at).total_seconds())
                        continue
                    raise EngineError(classify_error(e), redact(str(e))[:500],
                                      self._partial_usage(ctx, spawned_at)) from None
        except EngineError:
            if live:
                self.clear_live(ctx.attempt_key)
            raise
        if live:
            self.clear_live(ctx.attempt_key)

        ended = datetime.utcfromtimestamp(self._clock())
        try:
            result, reported = protocol.parse_response(raw)
        except protocol.ProtocolError as e:
            raise EngineError(ErrorCode.INTERNAL, f"invalid response: {e}", self._partial_usage(ctx, spawned_at)) from None

        measured = max((ended - spawned_at).total_seconds(), 0.0)
        exec_started = datetime.utcfromtimestamp(reported["exec_started_unix"])
        exec_ended = datetime.utcfromtimestamp(reported["exec_ended_unix"])
        # The container cannot claim more cold start than the time between spawn and its first byte
        cold = min(max(reported["cold_start_seconds"], 0.0), max((exec_started - spawned_at).total_seconds(), 0.0))
        usage = Usage(
            measured_seconds=measured,
            reported_seconds=reported["exec_seconds"] + cold,
            container_id=reported["container_id"],
            exec_started_at=exec_started,
            exec_ended_at=exec_ended,
            cold_start_seconds=cold,
            units={"media_seconds": result["duration"], "gpu": reported["gpu"], "model": reported["model"],
                   "compute_type": reported["compute_type"], "fingerprint": reported["fingerprint"]},
        )
        result["device"] = f"modal:{reported['gpu']}"
        return ExecResult(output=result, usage=usage)

    def lookup_attempt(self, attempt_key: str) -> Optional[Dict[str, Any]]:
        """{container_id, call_id, started_unix} once the container started the attempt (protocol 2)"""
        try:
            entry = self._state().get(protocol.attempt_entry(attempt_key))
        except Exception as e:
            logger.warning(f"[ENGINES] Could not read attempt {attempt_key} from {self.engine.get('slug')}: "
                           f"{redact(str(e))[:200]}")
            return None
        return entry if isinstance(entry, dict) else None

    def cancel(self, call_id: Optional[str], attempt_key: Optional[str]) -> None:
        """Stop spending on an attempt: the cooperative flag first, then the provider's cancel"""
        if attempt_key:
            try:
                self._state().put(protocol.cancel_entry(attempt_key), True)
            except Exception as e:
                logger.warning(f"[ENGINES] Could not flag attempt {attempt_key} for cancel: {redact(str(e))[:200]}")
        if call_id:
            try:
                self._call(call_id).cancel()
            except Exception as e:
                logger.warning(f"[ENGINES] Could not cancel call {call_id}: {redact(str(e))[:200]}")

    # --- deploy verification ------------------------------------------------------------------

    def deployed_meta(self) -> Dict[str, Any]:
        """Run the CPU-only meta() function: what is deployed (protocol, fingerprint). Costs seconds of CPU"""
        function = self.modal.Function.from_name(protocol.APP_NAME, protocol.META_FUNCTION,
                                                 environment_name=self.environment, client=self.client())
        return function.remote()

    def record_deployment(self, entry: Dict[str, Any]) -> None:
        self._state().put(protocol.DEPLOYMENT_KEY, entry)

    def subprocess_env(self, home: str, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        return provider_env(self._token_id, self._token_secret, home, environment=self.environment, extra=extra)

    # --- money --------------------------------------------------------------------------------

    def provider_spend(self, start: date, end: date) -> Decimal:
        """
        What the account reports as spent in [start, end) (UTC days), via the CLI in
        a subprocess with an allowlisted environment. Raises BillingError rather
        than ever answering 0 for something it could not read.
        """
        with tempfile.TemporaryDirectory(prefix="modal-home-") as home:
            command = [sys.executable, "-m", "modal", "billing", "report", "--start", start.isoformat(),
                       "--end", end.isoformat(), "--json"]
            try:
                done = self._run(command, env=self.subprocess_env(home), capture_output=True, text=True,
                                 timeout=BILLING_TIMEOUT_SECONDS, cwd=home)
            except subprocess.TimeoutExpired:
                raise BillingError("the billing report timed out") from None
            except OSError as e:
                raise BillingError(f"the billing report could not run ({type(e).__name__})") from None
        if done.returncode != 0:
            raise BillingError(f"the billing report failed: {redact((done.stderr or '').strip())[-300:]}")
        return parse_billing_report(done.stdout)
