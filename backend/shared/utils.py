"""
Utility functions for the application
"""
import hashlib


def calculate_file_checksum(file_contents: bytes) -> str:
    """
    Calculate SHA256 checksum of file contents for deduplication

    Args:
        file_contents: File contents as bytes

    Returns:
        str: SHA256 hash in hexadecimal format (64 characters)
    """
    return hashlib.sha256(file_contents).hexdigest()
