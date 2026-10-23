"""
422 INVALID_FILE_FORMAT on /upload and /convert: bytes that contradict the
extension are refused before any job exists, with a code a client can tell
apart from the generic 422 of a cut multipart upload (`body.file` missing).
"""
import pytest

from shared.models import Job
from tests.test_upload_projects import db, env, add_project, jwt, ALICE  # noqa: F401

BOUNDARY = "XyZb"


def _send(env, endpoint, filename, content):
    data = {"project": "P"}
    if endpoint == "/convert":
        data["source_type"] = "file"
    return env.client.post(endpoint, headers=jwt(), data=data,
                           files={"file": (filename, content, "application/octet-stream")})


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
@pytest.mark.parametrize("filename,content", [
    ("edital.pdf", b"<!DOCTYPE html><html>404 Not Found</html>"),
    ("edital.PDF", b"\x00\x01garbage"),
    ("anexo.docx", b"%PDF-1.4 a pdf renamed"),
    ("planilha.xls", b"PK\x03\x04 a zip, not OLE"),
    ("texto.rtf", b"plain text"),
])
def test_content_contradicting_the_extension_is_422_invalid_file_format(env, endpoint, filename, content):
    add_project(env.db, ALICE, "P")
    response = _send(env, endpoint, filename, content)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_FILE_FORMAT"
    assert env.db.query(Job).count() == 0
    assert env.enqueued == []
    assert [p for p in env.tmp.rglob("*") if p.is_file()] == []


@pytest.mark.parametrize("filename,content", [
    ("edital.pdf", b"%PDF-1.7\n..."),
    ("edital.pdf", b"\r\n" * 10 + b"%PDF-1.4\n"),  # junk before the header, within 1 KB
    ("anexo.docx", b"PK\x03\x04 zip"),
    ("antigo.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 ole"),
    ("texto.rtf", b"{\\rtf1\\ansi hi}"),
    ("pagina.html", b"anything goes"),
    ("sem-extensao", b"anything goes"),
])
def test_matching_or_unchecked_content_is_accepted(env, filename, content):
    add_project(env.db, ALICE, "P")
    response = _send(env, "/upload", filename, content)
    assert response.status_code == 200, response.text
    assert env.db.query(Job).count() == 1


def test_pdf_header_after_the_first_kilobyte_is_refused(env):
    add_project(env.db, ALICE, "P")
    response = _send(env, "/upload", "edital.pdf", b" " * 1024 + b"%PDF-1.4\n")
    assert response.json()["detail"]["code"] == "INVALID_FILE_FORMAT"


def test_cut_multipart_upload_keeps_the_validation_422_without_the_format_code(env):
    add_project(env.db, ALICE, "P")
    body = (f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"project\"\r\n\r\nP\r\n"
            f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"edital.pdf\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n%PDF-1.4 cut here").encode()
    response = env.client.post("/upload", content=body, headers={
        **jwt(), "Content-Type": f"multipart/form-data; boundary={BOUNDARY}"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail[0]["loc"] == ["body", "file"]
    assert env.db.query(Job).count() == 0
