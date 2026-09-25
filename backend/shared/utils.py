"""
Utility functions for the application
"""
import hashlib
from typing import Optional


def calculate_file_checksum(file_contents: bytes) -> str:
    """
    Calculate SHA256 checksum of file contents for deduplication

    Args:
        file_contents: File contents as bytes

    Returns:
        str: SHA256 hash in hexadecimal format (64 characters)
    """
    return hashlib.sha256(file_contents).hexdigest()


# Maximum length of a single path component on common filesystems (ext4, xfs)
MAX_FILENAME_BYTES = 255


def sanitize_upload_filename(filename: Optional[str]) -> str:
    """
    Reduce a client-supplied filename to a safe basename.

    The multipart filename is fully attacker-controlled; joining it to a path
    as-is allows "../" traversal or absolute paths (Path(a) / "/etc/x" == "/etc/x").
    The result is also capped at 255 UTF-8 bytes (keeping the extension) so long
    multi-byte names do not fail with ENAMETOOLONG.

    Args:
        filename: Filename sent by the client (may be None)

    Returns:
        str: Basename safe to join to a directory ("upload" if nothing usable is left)
    """
    name = (filename or "").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    if name in ("", ".", ".."):
        return "upload"

    if len(name.encode("utf-8")) > MAX_FILENAME_BYTES:
        stem, dot, ext = name.rpartition(".")
        if not dot or len(ext.encode("utf-8")) > 16:
            stem, ext = name, ""
        suffix = f".{ext}" if ext else ""
        budget = MAX_FILENAME_BYTES - len(suffix.encode("utf-8"))
        stem = stem.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
        name = stem + suffix

    return name
