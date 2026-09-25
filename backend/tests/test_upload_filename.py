"""Uploaded filenames must never escape the job's upload directory."""
from pathlib import Path

import pytest

from shared.utils import MAX_FILENAME_BYTES, sanitize_upload_filename

UPLOAD_DIR = Path("/tmp/ingestify/uploads/job-1")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("../../../../app/api/main.py", "main.py"),
        ("/etc/cron.d/x", "x"),
        ("..\\..\\windows\\win.ini", "win.ini"),
        ("a\x00b\n.pdf", "ab.pdf"),
        ("relatório final.pdf", "relatório final.pdf"),
    ],
)
def test_reduces_to_safe_basename(raw, expected):
    assert sanitize_upload_filename(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", ".", "..", "../", "dir/"])
def test_falls_back_when_nothing_usable_is_left(raw):
    assert sanitize_upload_filename(raw) == "upload"


@pytest.mark.parametrize(
    "raw",
    ["../../etc/passwd", "/abs/path.pdf", "..", "a/../../b.pdf", "C:\\..\\x.pdf"],
)
def test_result_stays_inside_upload_dir(raw):
    resolved = (UPLOAD_DIR / sanitize_upload_filename(raw)).resolve()
    assert resolved.parent == UPLOAD_DIR


def test_long_multibyte_name_is_capped_in_bytes_and_keeps_extension():
    name = sanitize_upload_filename("😀" * 200 + ".pdf")
    assert len(name.encode("utf-8")) <= MAX_FILENAME_BYTES
    assert name.endswith(".pdf")
    assert name.startswith("😀")  # no split multi-byte character


def test_long_name_without_extension_is_capped():
    name = sanitize_upload_filename("é" * 300)
    assert len(name.encode("utf-8")) <= MAX_FILENAME_BYTES
    assert set(name) == {"é"}
