"""
Media facts the router needs: which uploads are audio, and how long they last.

AUDIO_EXTENSIONS is the list process_conversion has always used to send a file
to Whisper; /upload and /convert use the same list to route audio once a
transcription route exists (spec 0003, R5). The probe reads a bounded prefix of
the file and never runs in the API process.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus', '.webm', '.wma', '.aac', '.oga', '.spx']


def is_audio_filename(name: Optional[str]) -> bool:
    return bool(name) and Path(name).suffix.lower() in AUDIO_EXTENSIONS


class ProbeLimitExceeded(Exception):
    """The probe tried to read more of the file than it is allowed to"""


class _BoundedReader:
    """A read-only file object that refuses to go past `limit` bytes"""

    def __init__(self, raw, limit: int):
        self.raw = raw
        self.limit = limit

    def read(self, size: int = -1) -> bytes:
        position = self.raw.tell()
        if position >= self.limit:
            raise ProbeLimitExceeded(f"probe stopped at {self.limit} bytes")
        allowed = self.limit - position
        size = allowed if size is None or size < 0 else min(size, allowed)
        return self.raw.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.raw.seek(offset, whence)

    def tell(self) -> int:
        return self.raw.tell()

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True


def probe_duration(path: str, max_bytes: int) -> Optional[float]:
    """
    Media duration in seconds from the container header, reading at most
    `max_bytes`; None when it cannot be told (unknown format, header past the
    limit, no PyAV). The caller bounds the time (the probe task's time limit).
    """
    try:
        import av  # only in worker images; never imported by the API
    except ImportError:
        return None
    try:
        with open(path, "rb") as raw, av.open(_BoundedReader(raw, max_bytes), mode="r") as container:
            if container.duration:
                return float(container.duration) / 1_000_000  # av.time_base
            stream = next(iter(container.streams.audio), None)
            if stream is not None and stream.duration and stream.time_base:
                return float(stream.duration * stream.time_base)
    except Exception as e:  # any parse failure means "unknown", never a failed job
        logger.info(f"[ENGINES] Could not probe {Path(path).name}: {type(e).__name__}")
    return None
