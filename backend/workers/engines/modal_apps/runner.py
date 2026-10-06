"""
What the Modal container does with one transcription request (spec 0003, 4.11).

Kept apart from whisper_app.py so it can be tested without `modal`: the
deployed class only loads the model and hands each request here, with the
account's state Dict and its own container id.

    1. validate the request (protocol.py), refuse a second spawn of the same attempt
       (put-if-absent of attempt:{key} -> container id: known even if the call dies)
    2. write the media to a temp file and run the shared Whisper loop (whisper_core)
    3. stop between segments past the request's deadline or when the worker set
       cancel:{key}
    4. with `live` (protocol 3), push decoded segments in batches to the live
       Queue, partition = the attempt key; best effort and bounded - a full or
       failing queue never fails the transcription
    5. answer the result plus usage: exec interval, cold start (first input of the
       container only), container id, GPU, model, compute type, fingerprint
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from workers.engines.modal_apps import protocol

# How often the cooperative cancel flag is read from the Dict (a network round trip)
CANCEL_POLL_SECONDS = 10.0


class Cancelled(RuntimeError):
    """Stopped on purpose: the deadline passed or the worker asked to stop"""


class LiveCaptions:
    """
    The container's side of live captions: buffer each decoded segment and push a
    batch every LIVE_FLUSH_SECONDS to the attempt's partition. Never blocks the
    decoding loop for long (non-blocking put) and never raises: after a failure,
    or once LIVE_MAX_BATCHES were pushed, it simply stops.
    """

    def __init__(self, queue, attempt_key: str, clock: Callable[[], float] = time.time):
        self.queue = queue
        self.partition = protocol.live_partition(attempt_key)
        self.clock = clock
        self.pending = []
        self.flushed_at = clock()
        self.batches = 0
        self.stopped = False

    def on_progress(self, transcribed_seconds: float, total_seconds: float, segment=None) -> None:
        if self.stopped or segment is None or not segment.get("text"):
            return
        self.pending.append(segment)
        if self.clock() - self.flushed_at >= protocol.LIVE_FLUSH_SECONDS or \
                len(self.pending) >= protocol.LIVE_MAX_SEGMENTS_PER_BATCH:
            self.flush()

    def flush(self) -> None:
        pending, self.pending = self.pending, []
        self.flushed_at = self.clock()
        if self.stopped or not pending:
            return
        if self.batches >= protocol.LIVE_MAX_BATCHES:
            self.stopped = True
            return
        try:
            self.queue.put(protocol.live_batch(pending), block=False, partition=self.partition,
                           partition_ttl=protocol.LIVE_PARTITION_TTL_SECONDS)
            self.batches += 1
        except Exception:
            self.stopped = True  # live text is cosmetic: the final result has every segment


def _is_media_error(exc: BaseException) -> bool:
    """PyAV failing to decode the upload: the input's fault, not the engine's"""
    module = type(exc).__module__ or ""
    return module == "av" or module.startswith("av.")


def handle(request_raw: Any, *, model, state, container_id: str, call_id: Optional[str], cold_start_seconds: float,
           gpu: str, fingerprint: str, transcribe: Optional[Callable] = None, clock: Callable[[], float] = time.time,
           tmp_dir: Optional[str] = None, live=None) -> Dict[str, Any]:
    request = protocol.parse_request(request_raw)
    key = request["attempt_key"]
    started = clock()

    if state is not None:
        entry = {"container_id": container_id, "call_id": call_id, "started_unix": started}
        if not state.put(protocol.attempt_entry(key), entry, skip_if_exists=True):
            existing = state.get(protocol.attempt_entry(key)) or {}
            if existing.get("call_id") != call_id:
                raise RuntimeError(f"{protocol.DUPLICATE_PREFIX} attempt {key} already ran in "
                                   f"{existing.get('container_id')}")

    deadline = request["deadline_unix"]
    polled = {"at": started}

    def should_cancel() -> bool:
        now = clock()
        if now >= deadline:
            return True
        if state is not None and now - polled["at"] >= CANCEL_POLL_SECONDS:
            polled["at"] = now
            try:
                return bool(state.get(protocol.cancel_entry(key)))
            except Exception:
                return False  # the provider's own cancel() still applies
        return False

    from workers.engines.runtime_security import require_safe_runtime
    # Remote inference is production even when the deployment CLI ran locally.
    require_safe_runtime(request["options"].get("transcriber_provider", "faster-whisper"), environment="production")

    if transcribe is None:
        if request['options'].get('transcriber_provider') == 'whisperx':
            from workers.engines import whisperx_core
            transcribe = whisperx_core.transcribe
        else:
            from workers.engines import whisper_core
            transcribe = whisper_core.transcribe
        if isinstance(model, dict):
            provider = request['options'].get('transcriber_provider', 'faster-whisper')
            if provider not in model:
                raise protocol.ProtocolError('DIARIZATION_NOT_READY: deployment capability unavailable')
            model = model[provider]

    captions = LiveCaptions(live, key, clock) if request["live"] and live is not None else None

    with tempfile.TemporaryDirectory(dir=tmp_dir) as work:
        path = Path(work) / f"media{request['suffix'] or '.bin'}"
        path.write_bytes(request["media"])
        del request["media"]
        extra = {"on_progress": captions.on_progress} if captions is not None else {}
        try:
            result = transcribe(model, path, request["options"], model_name=protocol.MODEL_NAME,
                                should_cancel=should_cancel, **extra)
        except Exception as exc:
            if type(exc).__name__ == "TranscriptionCancelled":
                raise Cancelled(f"CANCELLED: {exc}") from None
            if _is_media_error(exc):
                raise protocol.InputRejected(f"the media could not be decoded ({type(exc).__name__})") from None
            raise
        finally:
            if captions is not None:
                captions.flush()

    ended = clock()
    usage = {
        "exec_started_unix": started,
        "exec_ended_unix": ended,
        "exec_seconds": max(ended - started, 0.0),
        "cold_start_seconds": max(float(cold_start_seconds or 0), 0.0),
        "container_id": container_id,
        "gpu": gpu,
        "model": protocol.MODEL_NAME,
        "compute_type": protocol.COMPUTE_TYPE,
        "fingerprint": fingerprint,
        "protocol": protocol.PROTOCOL_VERSION,
    }
    return protocol.build_response(result, usage)


def container_id() -> str:
    """The Modal task (container) id, or a stand-in outside Modal"""
    return os.environ.get("MODAL_TASK_ID") or f"local-{os.getpid()}"
