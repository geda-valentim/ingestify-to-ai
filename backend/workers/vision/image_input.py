"""
Validation for caller-supplied image bytes, and the on-disk handoff to the worker.

The rungs of the ladder - decode, size, format - are here rather than inline in
the HTTP handlers so that the JSON route, the multipart route and the tasks all
apply exactly the same rules, and so that they can be tested without an ASGI
transport. They raise the same typed VisionError family as the rest of the
package, so a failure carries its HTTP status and error code with it.

Format is decided by sniffing magic bytes. A caller-supplied mime type is never
trusted: it is trivially forged and would let unexpected bytes reach PIL.

The handoff helpers at the bottom own the *layout* of that directory
(``<temp_storage_path>/images/<job_id>/<filename>``) so that the writer (the
API route), the deleter (the vision task) and the sweeper (the monitoring
backstop) cannot disagree about where the bytes live. They are here, and not in
``api/image_routes.py``, precisely because the process that creates the file is
not the process that removes it.

Nothing in this module imports torch, transformers or PIL - the API imports it,
and ``test_vision_import_safety.py`` keeps that true.
"""

import base64
import binascii
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple, Union

from workers.vision.errors import (
    ImagePayloadTooLargeError,
    InvalidImageBase64Error,
    VisionInvalidImageError,
)

logger = logging.getLogger(__name__)

# `data:image/png;base64,....` - stripped when present so a browser's
# canvas.toDataURL() output works without the caller having to trim it.
_DATA_URI_PREFIX = re.compile(r"^data:[^;,]{0,100};base64,", re.IGNORECASE)

_WHITESPACE = re.compile(r"\s+")

# (offset, signature, mime). Sniffed in order; first match wins.
_SIGNATURES: Tuple[Tuple[int, bytes, str], ...] = (
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
    (0, b"BM", "image/bmp"),
    (0, b"II*\x00", "image/tiff"),
    (0, b"MM\x00*", "image/tiff"),
)

SUPPORTED_MIME_TYPES = ("image/png", "image/jpeg", "image/webp", "image/bmp", "image/gif", "image/tiff")


def decode_base64_image(value: Optional[str]) -> bytes:
    """Decode the ``image_base64`` field into raw bytes.

    Accepts a bare base64 payload or a full data URI, and tolerates the line
    breaks MIME-style base64 carries.

    Raises:
        InvalidImageBase64Error: Empty, or not decodable as base64 (422).
    """
    if value is None or not str(value).strip():
        raise InvalidImageBase64Error(
            "image_base64 is empty. Send the raw base64 of the image bytes, "
            "optionally prefixed with a data: URI header."
        )

    payload = _DATA_URI_PREFIX.sub("", str(value).strip(), count=1)
    payload = _WHITESPACE.sub("", payload)

    if not payload:
        raise InvalidImageBase64Error(
            "image_base64 contains a data: URI header but no base64 payload."
        )

    try:
        # validate=True: reject anything outside the base64 alphabet instead of
        # silently discarding it, which would turn a truncated upload into a
        # confusing decode error much further downstream.
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImageBase64Error(
            f"image_base64 is not valid base64: {exc}. "
            "Send the raw base64 of the image bytes (a data: URI prefix is accepted)."
        ) from exc

    if not decoded:
        raise InvalidImageBase64Error("image_base64 decoded to zero bytes.")

    return decoded


def ensure_within_size_limit(data: bytes, max_size_mb: int) -> None:
    """Enforce the byte-size limit against the DECODED length.

    Checking the base64 string length instead would be wrong by a third, and
    images have their own limit - they must not inherit max_file_size_mb.

    Raises:
        ImagePayloadTooLargeError: Over the limit (413).
    """
    limit_bytes = max_size_mb * 1024 * 1024
    if len(data) > limit_bytes:
        raise ImagePayloadTooLargeError(
            f"Image is {len(data) / 1024 / 1024:.2f}MB, over the {max_size_mb}MB "
            "limit (VISION_MAX_IMAGE_SIZE_MB)."
        )


def sniff_image_mime(data: bytes) -> str:
    """Identify the image format from its magic bytes.

    Returns:
        One of SUPPORTED_MIME_TYPES.

    Raises:
        VisionInvalidImageError: Not a format we accept (422).
    """
    for offset, signature, mime in _SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            return mime

    # WEBP is a RIFF container: "RIFF" <4-byte length> "WEBP".
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    raise VisionInvalidImageError(
        "Unsupported image format. Accepted formats: "
        f"{', '.join(SUPPORTED_MIME_TYPES)}."
    )


def extension_for_mime(mime: str) -> str:
    """The filename suffix to store an image of this type under."""
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/gif": ".gif",
        "image/tiff": ".tiff",
    }.get(mime, ".bin")


# ---------------------------------------------------------------------------
# The on-disk handoff: one directory per job, deleted by whoever last read it
# ---------------------------------------------------------------------------

# Directory under `temp_storage_path` that holds the per-job handoff dirs.
IMAGE_HANDOFF_ROOT = "images"

# A job id is a uuid4 minted by the route. Rebuilding the path from it means a
# forged broker message cannot turn "delete the handoff" into "delete anything
# else": `../..` never matches.
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def image_handoff_root(temp_storage_path: Union[str, Path]) -> Path:
    """``<temp_storage_path>/images`` - the parent of every per-job directory."""
    return Path(temp_storage_path) / IMAGE_HANDOFF_ROOT


def image_handoff_dir(temp_storage_path: Union[str, Path], job_id: str) -> Path:
    """The directory holding one job's image.

    One directory per job, and a job id is a fresh uuid4 per request, so
    deleting a whole directory can never take a file another in-flight request
    is still using.

    Raises:
        ValueError: The job id is not a plain identifier (path traversal).
    """
    if not _SAFE_JOB_ID.match(str(job_id or "")):
        raise ValueError(f"refusing to build an image handoff path for job id {job_id!r}")
    return image_handoff_root(temp_storage_path) / str(job_id)


def discard_image_handoff(temp_storage_path: Union[str, Path], job_id: str) -> bool:
    """Delete one job's handoff directory. Never raises.

    Returns:
        True if a directory was removed, False if there was nothing to remove
        or the removal failed (which is logged, not raised - failing to clean
        up must never turn a successful inference into an error).
    """
    try:
        directory = image_handoff_dir(temp_storage_path, job_id)
    except ValueError as exc:
        logger.error("vision: %s", exc)
        return False

    try:
        if not directory.is_dir():
            return False
        shutil.rmtree(directory)
        logger.debug("vision: removed image handoff directory %s", directory)
        return True
    except OSError as exc:
        logger.warning("vision: could not remove image handoff %s: %s", directory, exc)
        return False


def sweep_image_handoffs(
    temp_storage_path: Union[str, Path], max_age_seconds: float
) -> int:
    """Remove handoff directories older than ``max_age_seconds``. Never raises.

    A BACKSTOP, not the mechanism. The primary deletion happens in the vision
    task's ``finally``; this only catches the case where that never ran at all -
    a hard time limit killing the worker process, a SIGKILL, or a message that
    was dispatched and never delivered. It is periodic, so it cannot bound a
    tight upload loop on its own.

    ``max_age_seconds`` must be comfortably longer than a task can legitimately
    hold its image, or this would delete a file out from under a running
    inference.

    Returns:
        The number of directories removed.
    """
    root = image_handoff_root(temp_storage_path)
    removed = 0

    try:
        if not root.is_dir():
            return 0
        entries = list(root.iterdir())
    except OSError as exc:
        logger.warning("vision: could not list image handoffs in %s: %s", root, exc)
        return 0

    cutoff = time.time() - max_age_seconds
    for entry in entries:
        try:
            if not entry.is_dir() or entry.stat().st_mtime > cutoff:
                continue
            shutil.rmtree(entry)
            removed += 1
            logger.info("vision: swept orphaned image handoff %s", entry)
        except OSError as exc:
            logger.warning("vision: could not sweep image handoff %s: %s", entry, exc)

    return removed
