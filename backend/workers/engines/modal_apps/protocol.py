"""
The wire contract between worker-remote and the deployed Modal app (spec 0003, 4.10).

Both sides import this file, so it depends on the standard library only (the
Modal image has no Ingestify settings, no pydantic). Messages are plain dicts
of primitives; each side validates what it receives with hard size limits, and
the worker never trusts the container's output beyond what is checked here (S7).

Protocol 2 (spec 0003, R12): when a container starts an input it writes
`attempt:{attempt_key} -> {container_id, call_id, started_unix}` into the
account's state Dict (put-if-absent), so the container is known even when the
call dies, and a second spawn of the same attempt refuses to run (gate T1).
The worker sets `cancel:{attempt_key}` to stop an input cooperatively; the
container checks it, and its own deadline, between decoded segments.
"""

from typing import Any, Dict, Optional, Tuple

PROTOCOL_VERSION = 2

APP_NAME = "ingestify-whisper"
CLS_NAME = "WhisperRunner"
META_FUNCTION = "meta"
STATE_DICT = "ingestify-whisper-state"
DEPLOYMENT_KEY = "deployment"

# The deployed Whisper (CTranslate2) weights, baked into the image
MODEL_NAME = "turbo"
MODEL_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
MODEL_REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
MODEL_DIR = "/models/whisper-turbo"
COMPUTE_TYPE = "float16"

# Limits (gate T1 verifies the provider's own input limit; ours stays below it)
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
MAX_SUFFIX_CHARS = 10
MAX_TEXT_CHARS = 5_000_000
MAX_SEGMENTS = 200_000
MAX_WORDS_PER_SEGMENT = 5_000
MAX_SEGMENT_TEXT_CHARS = 20_000
MAX_ID_CHARS = 128

# What a request may ask of Whisper; everything else is dropped
_OPTIONS = {
    "language": (str, type(None)),
    "include_word_timestamps": (bool,),
    "temperature": (int, float),
    "beam_size": (int,),
}

INPUT_REJECTED_PREFIX = "INPUT_REJECTED:"
DUPLICATE_PREFIX = "DUPLICATE_ATTEMPT:"


class ProtocolError(ValueError):
    """A message that does not follow the contract (wrong version, shape or size)"""


class InputRejected(ValueError):
    """The media itself cannot be transcribed (not decodable): retrying elsewhere will not help"""

    def __init__(self, detail: str):
        super().__init__(f"{INPUT_REJECTED_PREFIX} {detail}")


def attempt_entry(attempt_key: str) -> str:
    return f"attempt:{attempt_key}"


def cancel_entry(attempt_key: str) -> str:
    return f"cancel:{attempt_key}"


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def _number(value, name: str, low: float = 0.0, high: float = 10 ** 9) -> float:
    _check(isinstance(value, (int, float)) and not isinstance(value, bool), f"{name} must be a number")
    _check(low <= float(value) <= high, f"{name} out of range")
    return float(value)


def _text(value, name: str, limit: int, optional: bool = False) -> Optional[str]:
    if value is None and optional:
        return None
    _check(isinstance(value, str), f"{name} must be a string")
    _check(len(value) <= limit, f"{name} is longer than {limit} characters")
    return value


def clean_options(options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The Whisper options of a request, allowlisted and bounded"""
    clean: Dict[str, Any] = {}
    for name, types in _OPTIONS.items():
        value = (options or {}).get(name)
        if value is None:
            continue
        _check(isinstance(value, types) and not (name != "include_word_timestamps" and isinstance(value, bool)),
               f"option {name} has the wrong type")
        clean[name] = value
    if "language" in clean:
        _text(clean["language"], "language", 16)
    if "temperature" in clean:
        _number(clean["temperature"], "temperature", 0, 1)
    if "beam_size" in clean:
        _number(clean["beam_size"], "beam_size", 1, 10)
    return clean


# --- request: worker -> container -------------------------------------------------------


def build_request(*, attempt_key: str, media: bytes, suffix: str, options: Optional[Dict[str, Any]],
                  deadline_unix: float, max_media_bytes: int = MAX_MEDIA_BYTES) -> Dict[str, Any]:
    request = {
        "protocol": PROTOCOL_VERSION,
        "attempt_key": attempt_key,
        "suffix": suffix,
        "options": clean_options(options),
        "deadline_unix": float(deadline_unix),
        "media": media,
    }
    parse_request(request, max_media_bytes=max_media_bytes)
    return request


def parse_request(raw: Any, max_media_bytes: int = MAX_MEDIA_BYTES) -> Dict[str, Any]:
    _check(isinstance(raw, dict), "the request must be a dict")
    _check(raw.get("protocol") == PROTOCOL_VERSION,
           f"protocol {raw.get('protocol')!r} is not {PROTOCOL_VERSION}: redeploy the app")
    key = _text(raw.get("attempt_key"), "attempt_key", MAX_ID_CHARS)
    _check(bool(key), "attempt_key is empty")
    suffix = _text(raw.get("suffix") or "", "suffix", MAX_SUFFIX_CHARS)
    _check(suffix == "" or (suffix.startswith(".") and suffix[1:].isalnum()), "suffix must look like .mp3")
    media = raw.get("media")
    _check(isinstance(media, (bytes, bytearray)), "media must be bytes")
    _check(0 < len(media) <= max_media_bytes, f"media must be 1..{max_media_bytes} bytes")
    return {
        "protocol": PROTOCOL_VERSION,
        "attempt_key": key,
        "suffix": suffix,
        "options": clean_options(raw.get("options")),
        "deadline_unix": _number(raw.get("deadline_unix"), "deadline_unix", 0, 10 ** 11),
        "media": media if isinstance(media, bytes) else bytes(media),  # no copy of a large upload
    }


# --- response: container -> worker ------------------------------------------------------

_USAGE_NUMBERS = ("exec_started_unix", "exec_ended_unix", "exec_seconds", "cold_start_seconds")


def build_response(result: Dict[str, Any], usage: Dict[str, Any]) -> Dict[str, Any]:
    return {"protocol": PROTOCOL_VERSION, "result": result, "usage": usage}


def _segment(raw: Any, index: int) -> Dict[str, Any]:
    _check(isinstance(raw, dict), f"segment {index} must be a dict")
    segment = {
        "start": _number(raw.get("start"), f"segment {index} start"),
        "end": _number(raw.get("end"), f"segment {index} end"),
        "text": _text(raw.get("text"), f"segment {index} text", MAX_SEGMENT_TEXT_CHARS),
    }
    words = raw.get("words")
    if words is not None:
        _check(isinstance(words, list) and len(words) <= MAX_WORDS_PER_SEGMENT, f"segment {index} words")
        segment["words"] = [_word(w) for w in words]
    return segment


def _word(raw: Any) -> Dict[str, Any]:
    _check(isinstance(raw, dict), "a word must be a dict")
    return {
        "word": _text(raw.get("word"), "word", 512),
        "start": _number(raw.get("start"), "word start"),
        "end": _number(raw.get("end"), "word end"),
        "probability": _number(raw.get("probability"), "word probability", 0, 1),
    }


def parse_response(raw: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(result, usage) of a finished call; raises ProtocolError on anything unexpected"""
    _check(isinstance(raw, dict), "the response must be a dict")
    _check(raw.get("protocol") == PROTOCOL_VERSION, f"response protocol {raw.get('protocol')!r}")
    result, usage = raw.get("result"), raw.get("usage")
    _check(isinstance(result, dict) and isinstance(usage, dict), "result and usage must be dicts")

    segments = result.get("segments")
    _check(isinstance(segments, list) and len(segments) <= MAX_SEGMENTS, "segments")
    text = _text(result.get("text"), "text", MAX_TEXT_CHARS)
    clean_result = {
        "text": text,
        "segments": [_segment(s, i) for i, s in enumerate(segments)],
        "language": _text(result.get("language"), "language", 16, optional=True),
        "language_probability": _number(result.get("language_probability") or 0, "language_probability", 0, 1),
        "duration": _number(result.get("duration"), "duration"),
        "word_count": int(_number(result.get("word_count"), "word_count")),
        "char_count": int(_number(result.get("char_count"), "char_count")),
        "model": _text(result.get("model"), "model", 64),
        "provider": _text(result.get("provider"), "provider", 64),
    }

    clean_usage: Dict[str, Any] = {name: _number(usage.get(name), name, 0, 10 ** 11) for name in _USAGE_NUMBERS}
    _check(clean_usage["exec_ended_unix"] >= clean_usage["exec_started_unix"], "exec_ended before exec_started")
    clean_usage["container_id"] = _text(usage.get("container_id"), "container_id", MAX_ID_CHARS)
    for name in ("gpu", "model", "compute_type", "fingerprint"):
        clean_usage[name] = _text(usage.get(name), name, 128, optional=True)
    _check(usage.get("protocol") == PROTOCOL_VERSION, "usage protocol")
    clean_usage["protocol"] = PROTOCOL_VERSION
    return clean_result, clean_usage
