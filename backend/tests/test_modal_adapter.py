"""
The Modal side of remote engines (spec 0003, slice 4a), against a fake `modal`:
the wire protocol and its limits, what the container does with a request, the
fingerprint, the money arithmetic, and ModalAdapter - per-account clients (never
os.environ), the call id persisted before waiting, cancel at deadline_at, error
classification and a billing report parsed strictly (a missing field is an
error, never 0). Nothing here touches the network.
"""

import os
import subprocess
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from shared.engines import pricing
from shared.engines.capacity import Binding, deploy_state
from tests._fake_modal import Clock, FakeModal, response_for
from workers.engines.adapters import modal as modal_adapter
from workers.engines.adapters.modal import BillingError, ModalAdapter, classify_error, parse_billing_report
from workers.engines.base import EngineError, ErrorCode, ExecutionContext
from workers.engines.modal_apps import fingerprint, protocol, runner

TOKEN_ID = "ak-TestTokenId0123456789"
TOKEN_SECRET = "as-TestTokenSecret0123456789abc"
L4 = Binding(gpu_type="L4", workers=1)


def adapter(fake=None, clock=None, run=subprocess.run, **engine):
    fake = fake or FakeModal()
    snapshot = {"id": "eng-m1", "slug": "modal_1", "config": {}, "deployments": {}, **engine}
    return ModalAdapter(snapshot, {"token_id": TOKEN_ID, "token_secret": TOKEN_SECRET}, modal_module=fake,
                        clock=clock or Clock(), run=run), fake


def context(**overrides):
    calls = {"recorded": [], "beats": 0}

    def record(call_id, spawned_at, deadline_at):
        calls["recorded"].append((call_id, spawned_at, deadline_at))

    def beat():
        calls["beats"] += 1
        return True

    values = dict(usage_id=7, attempt_key="attempt-1", record_call_id=record, heartbeat=beat)
    values.update(overrides)
    return ExecutionContext(**values), calls


# --- protocol ------------------------------------------------------------------------------------


def test_a_request_keeps_only_allowlisted_options_and_bounds_the_media():
    request = protocol.build_request(attempt_key="k", media=b"ID3...", suffix=".mp3", deadline_unix=2_000.0,
                                     options={"language": "pt", "beam_size": 5, "auth_token": "eyJ...",
                                              "include_word_timestamps": True})
    assert request["options"] == {"language": "pt", "beam_size": 5, "include_word_timestamps": True}
    with pytest.raises(protocol.ProtocolError, match="media"):
        protocol.build_request(attempt_key="k", media=b"x" * 11, suffix=".mp3", options={}, deadline_unix=1.0,
                               max_media_bytes=10)
    with pytest.raises(protocol.ProtocolError, match="suffix"):
        protocol.build_request(attempt_key="k", media=b"x", suffix="/etc/passwd", options={}, deadline_unix=1.0)
    with pytest.raises(protocol.ProtocolError, match="protocol"):
        protocol.parse_request({**request, "protocol": 1})


def test_a_response_is_validated_before_anything_is_stored():
    result, usage = protocol.parse_response(response_for({}))
    assert result["text"] == "olá mundo" and usage["container_id"] == "ta-container-1"

    bad = response_for({})
    bad["result"]["segments"] = [{"start": 0, "end": 1}]  # no text
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_response(bad)
    bad = response_for({})
    bad["usage"]["exec_ended_unix"] = 0  # ends before it starts
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_response(bad)
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_response({"protocol": 2, "result": "rm -rf", "usage": {}})


# --- the container's handler ---------------------------------------------------------------------


class FakeState(dict):
    def put(self, key, value, *, skip_if_exists=False):
        if skip_if_exists and key in self:
            return False
        self[key] = value
        return True


def fake_transcribe(seen):
    def transcribe(model, path, options, *, model_name, should_cancel):
        seen.append((Path(path).read_bytes(), options, model_name))
        return {"text": "oi", "segments": [{"start": 0.0, "end": 1.0, "text": "oi"}], "language": "pt",
                "language_probability": 0.9, "duration": 1.0, "word_count": 1, "char_count": 2, "model": model_name,
                "provider": "faster-whisper"}
    return transcribe


def test_the_container_records_its_attempt_and_reports_usage():
    seen, state, clock = [], FakeState(), Clock(step=5.0)
    request = protocol.build_request(attempt_key="k1", media=b"media", suffix=".mp3", options={"language": "pt"},
                                     deadline_unix=10_000.0)
    raw = runner.handle(request, model=object(), state=state, container_id="ta-1", call_id="fc-1",
                        cold_start_seconds=9.5, gpu="L4", fingerprint="f" * 64, transcribe=fake_transcribe(seen),
                        clock=clock)
    result, usage = protocol.parse_response(raw)
    assert seen == [(b"media", {"language": "pt"}, "turbo")]
    assert state[protocol.attempt_entry("k1")]["container_id"] == "ta-1"
    assert usage["cold_start_seconds"] == 9.5 and usage["exec_seconds"] == 5.0 and usage["gpu"] == "L4"

    # A second spawn of the same attempt (another call) refuses to run (gate T1: put-if-absent)
    with pytest.raises(RuntimeError, match=protocol.DUPLICATE_PREFIX):
        runner.handle(request, model=object(), state=state, container_id="ta-2", call_id="fc-2",
                      cold_start_seconds=0, gpu="L4", fingerprint="f", transcribe=fake_transcribe(seen), clock=clock)


def test_the_container_stops_at_its_deadline_or_when_asked():
    from workers.engines.whisper_core import TranscriptionCancelled

    def slow(model, path, options, *, model_name, should_cancel):
        for _ in range(100):
            if should_cancel():
                raise TranscriptionCancelled("stopped")
        raise AssertionError("never stopped")

    clock = Clock(start=0.0, step=4.0)
    request = protocol.build_request(attempt_key="k", media=b"m", suffix=".mp3", options={}, deadline_unix=20.0)
    with pytest.raises(runner.Cancelled):
        runner.handle(request, model=None, state=None, container_id="c", call_id=None, cold_start_seconds=0,
                      gpu="L4", fingerprint="f", transcribe=slow, clock=clock)

    state = FakeState({protocol.cancel_entry("k2"): True})
    request = protocol.build_request(attempt_key="k2", media=b"m", suffix=".mp3", options={}, deadline_unix=1e9)
    with pytest.raises(runner.Cancelled):
        runner.handle(request, model=None, state=state, container_id="c", call_id="fc", cold_start_seconds=0,
                      gpu="L4", fingerprint="f", transcribe=slow, clock=Clock(start=0.0, step=4.0))


def test_undecodable_media_is_the_inputs_fault():
    InvalidData = type("InvalidDataError", (Exception,), {"__module__": "av.error"})

    def broken(model, path, options, *, model_name, should_cancel):
        raise InvalidData("bad header")

    request = protocol.build_request(attempt_key="k", media=b"m", suffix=".mp3", options={}, deadline_unix=1e9)
    with pytest.raises(protocol.InputRejected) as exc:
        runner.handle(request, model=None, state=None, container_id="c", call_id=None, cold_start_seconds=0,
                      gpu="L4", fingerprint="f", transcribe=broken)
    assert classify_error(exc.value) == ErrorCode.INPUT_REJECTED


# --- fingerprint and money -----------------------------------------------------------------------


def test_the_fingerprint_covers_the_binding_and_cpu():
    base = fingerprint.expected_fingerprint("transcription", {}, L4)
    assert base == fingerprint.expected_fingerprint("transcription", {}, Binding(gpu_type="L4", workers=1))
    assert len(base) == 64
    for other in (Binding(gpu_type="T4", workers=1), Binding(gpu_type="L4", workers=2),
                  Binding(gpu_type="L4", workers=1, cpu=4)):
        assert fingerprint.expected_fingerprint("transcription", {}, other) != base
    assert fingerprint.expected_fingerprint("transcription", {"max_media_seconds": 7200}, L4) != base  # memory, timeout

    deployments = {"transcription": {"binding": L4.model_dump(exclude_none=True), "fingerprint": base}}
    assert deploy_state("modal", deployments, "transcription", L4, base) == "deployed"
    assert deploy_state("modal", deployments, "transcription", L4, "0" * 64) == "needs_redeploy"  # code changed


def test_rate_hold_and_settle_are_decimal_and_rounded_up():
    rate = pricing.rate_usd_per_s({}, L4)
    # L4 + 2 cores + 6.3 GiB (4 h admissible media): about 0.000262 US$/s
    assert Decimal("0.00025") < rate < Decimal("0.00028")
    hold = pricing.hold_usd({}, L4, 1980)  # a 33 min lesson, cold, worst case
    assert hold == pricing.round_up((Decimal(str(1980 / 10 + 15 + 30))) * rate * Decimal("1.2"))
    assert Decimal("0.06") < hold < Decimal("0.09")
    assert pricing.settle_usd(100, 130, rate) == pricing.round_up(Decimal("130") * rate)
    assert pricing.settle_usd(130, 100, rate) == pricing.round_up(Decimal("130") * rate)  # never cheaper than reported
    assert pricing.deadline_seconds(hold, rate) == pytest.approx(float(hold / rate))
    decorator = pricing.modal_decorator({}, L4)
    assert decorator["min_containers"] == 0 and decorator["max_containers"] == 1 and decorator["cpu"] == 2.0


# --- the adapter ---------------------------------------------------------------------------------


def test_credentials_go_to_a_per_account_client_never_to_the_environment(monkeypatch):
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    a, fake = adapter()
    report = a.test_connection()
    assert report.ok and report.deployed is True
    assert fake.clients == [(TOKEN_ID, TOKEN_SECRET)]
    assert "MODAL_TOKEN_ID" not in os.environ and "MODAL_TOKEN_SECRET" not in os.environ
    assert TOKEN_SECRET not in repr(a)


def test_connection_test_reports_auth_and_missing_deploys_without_a_container():
    a, fake = adapter()
    fake.account(TOKEN_ID).deployed = False
    report = a.test_connection()
    assert report.ok and report.deployed is False and fake.account(TOKEN_ID).spawned == []

    fake.account(TOKEN_ID).auth_error = "Token is invalid"
    report = a.test_connection()
    assert not report.ok and report.code == ErrorCode.AUTH


def test_execute_records_the_call_before_waiting_and_measures_usage():
    clock = Clock(start=1_000.0)
    a, fake = adapter(clock=clock)
    account = fake.account(TOKEN_ID)
    account.clock = clock
    account.behaviour = lambda request: (2, response_for(request, started=1_010.0, cold=40.0, exec_seconds=100.0))
    ctx, calls = context()
    result = a.execute(media=b"ID3 audio", suffix=".mp3", options={"language": "pt"}, ctx=ctx, budget_seconds=300)

    assert calls["recorded"][0][0] == "fc-1"  # persisted before the first get()
    assert calls["recorded"][0][2] == datetime.utcfromtimestamp(1_300.0)  # deadline = spawn + reserved / rate
    assert calls["beats"] == 2  # one heartbeat per 15 s slice without output
    assert result.output["text"] == "olá mundo" and result.output["device"] == "modal:L4"
    assert result.usage.container_id == "ta-container-1"
    assert result.usage.cold_start_seconds == 10.0  # clamped to exec_started - spawned
    assert result.usage.reported_seconds == 110.0 and result.usage.measured_seconds == 30.0
    assert account.spawned[0]["deadline_unix"] == 1_300.0


def test_a_call_that_never_returns_is_cancelled_at_its_deadline():
    clock = Clock(start=1_000.0)
    a, fake = adapter(clock=clock)
    account = fake.account(TOKEN_ID)
    account.clock = clock
    account.behaviour = lambda request: (None, None)  # never finishes
    ctx, _ = context()
    with pytest.raises(EngineError) as exc:
        a.execute(media=b"audio", suffix=".mp3", options={}, ctx=ctx, budget_seconds=100)
    assert exc.value.code == ErrorCode.TIMEOUT
    call = account.calls["fc-1"]
    assert call.cancelled and account.state[protocol.cancel_entry("attempt-1")] is True
    assert exc.value.usage.container_id == "ta-container-1"  # known even on failure (protocol 2)
    assert exc.value.usage.measured_seconds <= 100 + 15  # at most one poll past the deadline
    assert sum(call.gets) <= 100 + 1e-6


def test_a_failing_call_is_classified_and_keeps_its_container():
    a, fake = adapter()
    fake.account(TOKEN_ID).behaviour = lambda request: (0, RuntimeError("CUDA out of memory"))
    ctx, _ = context()
    with pytest.raises(EngineError) as exc:
        a.execute(media=b"a", suffix=".mp3", options={}, ctx=ctx, budget_seconds=100)
    assert exc.value.code == ErrorCode.INTERNAL and exc.value.usage.container_id == "ta-container-1"

    fake.account(TOKEN_ID).deployed = False
    with pytest.raises(EngineError) as exc:
        a.execute(media=b"a", suffix=".mp3", options={}, ctx=context()[0], budget_seconds=100)
    assert exc.value.code == ErrorCode.NOT_DEPLOYED


def test_an_invalid_response_is_an_internal_error():
    a, fake = adapter()
    fake.account(TOKEN_ID).behaviour = lambda request: (0, {"protocol": 2, "result": {}, "usage": {}})
    with pytest.raises(EngineError) as exc:
        a.execute(media=b"a", suffix=".mp3", options={}, ctx=context()[0], budget_seconds=100)
    assert exc.value.code == ErrorCode.INTERNAL and "invalid response" in exc.value.detail


@pytest.mark.parametrize("exc, code", [
    (FakeModal().exception.AuthError("bad"), ErrorCode.AUTH),
    (Exception("Token ak-123 is invalid"), ErrorCode.AUTH),
    (FakeModal().exception.ResourceExhaustedError("Workspace spending limit reached for this billing cycle"),
     ErrorCode.QUOTA_EXHAUSTED),
    (FakeModal().exception.ConflictError("Workspace acme is disabled"), ErrorCode.QUOTA_EXHAUSTED),
    (FakeModal().exception.NotFoundError("App 'ingestify-whisper' not found"), ErrorCode.NOT_DEPLOYED),
    (FakeModal().exception.ResourceExhaustedError("rate limit exceeded"), ErrorCode.CAPACITY),
    (FakeModal().exception.FunctionTimeoutError("Function timed out"), ErrorCode.TIMEOUT),
    (FakeModal().exception.OutputExpiredError(), ErrorCode.LOST),
    (ConnectionError("connection reset"), ErrorCode.TRANSIENT),
    (protocol.InputRejected("the media could not be decoded"), ErrorCode.INPUT_REJECTED),
    (RuntimeError("CUDA out of memory"), ErrorCode.INTERNAL),
])
def test_classify_error(exc, code):
    assert classify_error(exc) == code


# --- billing -------------------------------------------------------------------------------------


def test_the_billing_report_is_parsed_strictly():
    assert parse_billing_report('[{"object_id": "ap-1", "cost": "1.25"}, {"cost": "0.75"}]') == Decimal("2.00")
    assert parse_billing_report("[]") == Decimal("0")  # a period without spend
    for bad in ('[{"Cost": "1.0"}]', '[{"object_id": "ap-1"}]', '{"cost": 1}', "not json", '[{"cost": "NaN"}]',
                '[{"cost": "-1"}]'):
        with pytest.raises(BillingError):
            parse_billing_report(bad)


def test_the_billing_subprocess_gets_an_allowlisted_environment_and_no_token_in_argv(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "must-not-leak-into-the-subprocess-0123456789")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://root:pw@db/ingestify")
    seen = {}

    def run(command, env, **kwargs):
        seen.update(command=command, env=env)
        return SimpleNamespace(returncode=0, stdout='[{"cost": "3.5"}]', stderr="")

    a, _ = adapter(run=run, config={"modal_environment": "main"})
    assert a.provider_spend(date(2026, 10, 1), date(2026, 11, 1)) == Decimal("3.5")
    assert set(seen["env"]) <= {"PATH", "LANG", "HOME", "PYTHONPATH", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET",
                                "MODAL_ENVIRONMENT"}
    assert seen["env"]["MODAL_TOKEN_SECRET"] == TOKEN_SECRET and seen["env"]["MODAL_ENVIRONMENT"] == "main"
    assert not any(TOKEN_SECRET in part or TOKEN_ID in part for part in seen["command"])
    assert seen["command"][-5:] == ["--start", "2026-10-01", "--end", "2026-11-01", "--json"]
    assert seen["env"]["HOME"] != os.environ.get("HOME")

    def failing(command, env, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr=f"auth failed for {TOKEN_SECRET}")

    a, _ = adapter(run=failing)
    with pytest.raises(BillingError) as exc:
        a.provider_spend(date(2026, 10, 1), date(2026, 11, 1))
    assert TOKEN_SECRET not in str(exc.value)


def test_importing_the_adapter_does_not_import_modal():
    import sys
    assert modal_adapter is not None
    assert "modal" not in sys.modules
