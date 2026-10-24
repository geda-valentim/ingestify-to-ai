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


@pytest.fixture
def app_env(env):
    """`env` with the API's validation handler (api/main.py), as in production."""
    from fastapi.exceptions import RequestValidationError
    from api.main import validation_exception_handler

    env.client.app.add_exception_handler(RequestValidationError, validation_exception_handler)
    return env


def test_cut_multipart_upload_is_422_file_missing(app_env):
    env = app_env
    add_project(env.db, ALICE, "P")
    body = (f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"project\"\r\n\r\nP\r\n"
            f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"edital.pdf\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n%PDF-1.4 cut here").encode()
    response = env.client.post("/upload", content=body, headers={
        **jwt(), "Content-Type": f"multipart/form-data; boundary={BOUNDARY}"})
    assert response.status_code == 422
    assert response.json()["code"] == "FILE_MISSING"
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail[0]["loc"] == ["body", "file"]
    assert env.db.query(Job).count() == 0


def test_other_validation_errors_are_validation_error(app_env):
    add_project(app_env.db, ALICE, "P")
    response = app_env.client.post("/upload", headers=jwt(), data={"project": "P", "image_mode": "bogus"},
                                   files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert isinstance(response.json()["detail"], list)


def _code(response):
    return response.status_code, response.json()["detail"]["code"]


def test_empty_and_too_large_files_carry_their_code(env, monkeypatch):
    from api import routes

    add_project(env.db, ALICE, "P")
    assert _code(_send(env, "/upload", "a.pdf", b"")) == (400, "FILE_EMPTY")
    monkeypatch.setattr(routes.settings, "max_file_size_mb", 0)
    assert _code(_send(env, "/upload", "a.pdf", b"%PDF-1.4")) == (413, "FILE_TOO_LARGE")


def test_invalid_tags_carry_their_code(env):
    add_project(env.db, ALICE, "P")
    response = env.client.post("/upload", headers=jwt(), data={"project": "P", "tags": "x" * 500},
                               files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert _code(response) == (422, "INVALID_TAGS")


@pytest.mark.parametrize("data,files,headers,expected", [
    ({"source_type": "ftp", "source": "x"}, None, {}, "INVALID_SOURCE_TYPE"),
    ({"source_type": "file"}, None, {}, "FILE_REQUIRED"),
    ({"source_type": "url"}, None, {}, "SOURCE_REQUIRED"),
    ({"source_type": "gdrive", "source": "abc"}, None, {}, "SOURCE_TOKEN_REQUIRED"),
])
def test_convert_400s_carry_their_code(env, data, files, headers, expected):
    add_project(env.db, ALICE, "P")
    response = env.client.post("/convert", headers={**jwt(), **headers}, data={"project": "P", **data})
    assert _code(response) == (400, expected)


@pytest.mark.parametrize("data,filename,expected", [
    ({"output_format": "docx"}, "talk.mp3", (422, "INVALID_OUTPUT_FORMAT")),
    ({}, "talk.pdf", (422, "UNSUPPORTED_MEDIA_FORMAT")),
])
def test_transcribe_refusals_carry_their_code(env, data, filename, expected):
    add_project(env.db, ALICE, "P")
    response = env.client.post("/transcribe", headers=jwt(), data={"project": "P", **data},
                               files={"file": (filename, b"ID3audio", "application/octet-stream")})
    assert _code(response) == expected


def test_transcription_disabled_carries_its_code(env, monkeypatch):
    from api import routes

    monkeypatch.setattr(routes.settings, "enable_audio_transcription", False)
    response = env.client.post("/transcribe", headers=jwt(), data={"project": "P"},
                               files={"file": ("talk.mp3", b"ID3audio", "audio/mpeg")})
    assert _code(response) == (503, "TRANSCRIPTION_DISABLED")


@pytest.mark.parametrize("path", ["/upload", "/convert", "/transcribe"])
def test_swagger_lists_the_codes_of_each_status(env, path):
    responses = env.client.app.openapi()["paths"][path]["post"]["responses"]
    assert {"400", "404", "413", "422", "500", "503"} <= set(responses)
    assert "FOLDER_LIMIT" in responses["422"]["description"]
    assert "FILE_MISSING" in responses["422"]["description"]
    assert responses["422"]["content"]["application/json"]["example"]["detail"]["code"]


def test_image_routes_keep_their_envelope_for_invalid_tags(env, monkeypatch):
    add_project(env.db, ALICE, "P")
    response = env.client.post("/images/describe/upload", headers=jwt(), data={"project": "P", "tags": "x" * 500},
                               files={"file": ("foto.png", b"\x89PNG\r\n\x1a\n", "image/png")})
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "INVALID_TAGS"


def test_health_reports_the_api_version(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from api import routes
    from api.openapi_docs import API_VERSION

    monkeypatch.setattr(routes, "get_redis_client", lambda: SimpleNamespace(ping=lambda: True))
    monkeypatch.setattr(routes, "get_es_client", lambda: SimpleNamespace(health_check=lambda: True))
    from workers.celery_app import celery_app
    monkeypatch.setattr(celery_app.control, "inspect", lambda: SimpleNamespace(stats=lambda: {"w1": {}}))
    assert asyncio.run(routes.health_check()).version == API_VERSION
