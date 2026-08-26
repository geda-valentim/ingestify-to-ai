"""
Validation for caller-supplied image bytes.

The rungs of the ladder - decode, size, format - are here rather than inline in
the HTTP handlers so that the JSON route, the multipart route and the tasks all
apply exactly the same rules, and so that they can be tested without an ASGI
transport. They raise the same typed VisionError family as the rest of the
package, so a failure carries its HTTP status and error code with it.

Format is decided by sniffing magic bytes. A caller-supplied mime type is never
trusted: it is trivially forged and would let unexpected bytes reach PIL.
"""

import base64
import binascii
import re
from typing import Optional, Tuple

from workers.vision.errors import (
    ImagePayloadTooLargeError,
    InvalidImageBase64Error,
    VisionInvalidImageError,
)

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
