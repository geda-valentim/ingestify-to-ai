"""Bilingual API text, English by default (P-13 slice 1).

- Accept-Language negotiation (en/pt, quality values, fallbacks);
- Content-Language and Vary on every response;
- the language reaches sync endpoints (threadpool), async endpoints and nested
  dependencies; outside a request it is English;
- a refusal keeps its `code` in both languages, only `message` changes.
"""

import asyncio

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from shared.error_catalog import render
from shared.i18n import LanguageMiddleware, api_error, current_lang, negotiate, use_lang


@pytest.mark.parametrize("header,expected", [
    ("pt-BR", "pt"),
    ("pt", "pt"),
    ("pt-PT;q=0.8", "pt"),
    ("PT-br", "pt"),
    ("fr, pt;q=0.5", "pt"),
    ("en;q=0.1, pt;q=0.9", "pt"),
    ("pt;q=0.5, en;q=0.9", "en"),
    ("pt, en", "pt"),
    ("en, pt", "en"),
    ("pt;q=0", "en"),
    ("pt;q=0, en;q=0.2", "en"),
    ("pt;q=abc", "pt"),
    ("*", "en"),
    ("fr, de;q=0.7", "en"),
    ("", "en"),
    (None, "en"),
    (";;;,,,", "en"),
    ("\x00\xff garbage", "en"),
])
def test_negotiate(header, expected):
    assert negotiate(header) == expected


def test_outside_a_request_the_language_is_english():
    assert current_lang() == "en"
    assert render("FILE_EMPTY") == "The uploaded file is empty."


def test_use_lang_scopes_the_language_and_restores_it():
    with use_lang("pt"):
        assert render("FILE_EMPTY") == "Arquivo enviado está vazio"
        with use_lang("klingon"):
            assert current_lang() == "en"
        assert current_lang() == "pt"
    assert current_lang() == "en"


def test_render_falls_back_to_the_other_language_then_to_the_code():
    # Engine-control entries without English yet answer in Portuguese for English clients.
    assert "Vincule um perfil" in render("RUNTIME_PROFILE_REQUIRED")
    assert render("NOT_A_REAL_CODE") == "NOT_A_REAL_CODE"
    assert render("FILE_TOO_LARGE", lang="pt", max_size_mb=7) == "Arquivo muito grande. Máximo: 7MB"
    assert render("FILE_TOO_LARGE", lang="en", max_size_mb=7) == "The file is too large. Maximum size: 7 MB."


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(LanguageMiddleware)

    def dependency_that_raises():
        raise api_error(409, "FILE_EMPTY")

    @app.get("/sync")
    def sync_endpoint():  # runs in the threadpool
        raise api_error(400, "FILE_EMPTY")

    @app.get("/async")
    async def async_endpoint():
        await asyncio.sleep(0)
        raise api_error(400, "FILE_EMPTY")

    @app.get("/dep", dependencies=[Depends(dependency_that_raises)])
    def with_dependency():
        return {}

    @app.get("/ok")
    def ok():
        return {"lang": current_lang()}

    return TestClient(app)


@pytest.mark.parametrize("path", ["/sync", "/async", "/dep"])
def test_sync_async_and_dependency_endpoints_render_the_request_language(client, path):
    default = client.get(path)
    portuguese = client.get(path, headers={"Accept-Language": "pt-BR"})
    assert default.json()["detail"] == {"code": "FILE_EMPTY", "message": "The uploaded file is empty."}
    assert portuguese.json()["detail"] == {"code": "FILE_EMPTY", "message": "Arquivo enviado está vazio"}
    assert default.status_code == portuguese.status_code


def test_language_headers_are_on_every_response(client):
    r = client.get("/ok")
    assert r.json() == {"lang": "en"}
    assert r.headers["content-language"] == "en"
    assert "Accept-Language" in r.headers["vary"]
    r = client.get("/ok", headers={"Accept-Language": "pt-BR,pt;q=0.9"})
    assert r.json() == {"lang": "pt"}
    assert r.headers["content-language"] == "pt-BR"
    missing = client.get("/missing", headers={"Accept-Language": "pt"})
    assert missing.status_code == 404 and missing.headers["content-language"] == "pt-BR"


def test_requests_do_not_leak_their_language_into_each_other(client):
    assert client.get("/ok", headers={"Accept-Language": "pt"}).json() == {"lang": "pt"}
    assert client.get("/ok").json() == {"lang": "en"}


def test_every_param_of_a_template_reaches_the_message():
    assert render("PAGES_FAILED", lang="en", failed=2, total=5).startswith("2 of 5 pages failed")
    assert render("PAGES_FAILED", lang="pt", failed=2, total=5).startswith("2 de 5 páginas falharam")
