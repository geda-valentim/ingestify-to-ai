"""The rest of the routes, auth and rate limits answer in the request language (P-13 slice 2).

Each case asserts the same status and `code` in English (the default) and in
pt-BR, and that only `message` changes.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import auth_routes, deps
from shared import rate_limit
from shared.auth import get_current_user
from shared.database import get_db
from shared.i18n import LanguageMiddleware, use_lang
from tests.test_iam_data_routes import ALICE, BOB, KEY_A, client, db, mode, no_shadow_noise  # noqa: F401
from tests.test_login_rate_limit import FakeRedis, USER, credentials, redis, request  # noqa: F401

PT = {"Accept-Language": "pt-BR"}
EN = {}


def _both(call):
    """(response in English by default, response in pt-BR)."""
    return call(EN), call(PT)


def _coded(response, status, code):
    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code and isinstance(detail["message"], str) and detail["message"]
    return detail["message"]


def _same_code_other_text(call, status, code, en_text, pt_text):
    en, pt = _both(call)
    assert _coded(en, status, code) == en_text
    assert _coded(pt, status, code) == pt_text


# -- jobs --------------------------------------------------------------------------------


def test_expired_job_is_a_localized_text_404(client):  # noqa: F811
    """After authorization: the owner's job whose cache entry is gone."""
    path = "/jobs/job-a/transcript/partial"
    en = client(ALICE).get(path)
    pt = client(ALICE).get(path, headers=PT)
    assert (en.status_code, en.json()["detail"]) == (404, "Job not found or expired")
    assert (pt.status_code, pt.json()["detail"]) == (404, "Job não encontrado ou expirado")


@pytest.mark.parametrize("lang", [EN, PT])
def test_foreign_and_missing_job_are_identical_on_the_expiry_paths(client, lang):  # noqa: F811
    for path in ("/jobs/{}/transcript/partial", "/jobs/{}/result", "/jobs/{}/pages", "/jobs/{}/pages/1/status",
                 "/jobs/{}/assets/x.png", "/jobs/{}/source"):
        method = "delete" if path.endswith("/source") else "get"
        foreign = getattr(client(BOB), method)(path.format("job-a"), headers=lang)
        missing = getattr(client(BOB), method)(path.format("missing"), headers=lang)
        assert foreign.status_code == missing.status_code == 404, path
        assert foreign.json() == missing.json(), path


def test_page_and_list_refusals_are_coded_in_both_languages(client):  # noqa: F811
    _same_code_other_text(
        lambda h: client(ALICE).get("/jobs/job-a/pages/9/status", headers=h), 404, "PAGE_NOT_FOUND_IN_JOB",
        "Page 9 was not found in job job-a. Check that the job is a multi-page PDF and that the page exists.",
        "Página 9 não encontrada no job job-a. Verifique se o job é um PDF multi-página e se a página existe.",
    )
    _same_code_other_text(
        lambda h: client(ALICE).get("/jobs", params={"status": "bogus"}, headers=h), 422, "JOB_STATUS_INVALID",
        "Invalid status: bogus", "status inválido: bogus",
    )
    en, pt = _both(lambda h: client(ALICE).get("/jobs", params={"folder_id": "root"}, headers=h))
    assert _coded(en, 422, "FOLDER_ROOT_NEEDS_PROJECT") == "folder_id=root requires project_id."
    assert _coded(pt, 422, "FOLDER_ROOT_NEEDS_PROJECT") == "folder_id=root exige project_id"


def test_source_and_retry_refusals_are_coded_in_both_languages(client):  # noqa: F811
    _same_code_other_text(
        lambda h: client(ALICE).delete("/jobs/job-a/source", headers=h), 404, "SOURCE_NOT_FOUND",
        "The original file was not found.", "Arquivo original não encontrado",
    )
    en, pt = _both(lambda h: client(ALICE).post("/jobs/job-a/pages/1/retry", headers=h))
    assert _coded(en, 400, "PAGE_NOT_FAILED") == "Page 1 is not in 'failed' status (current status: completed)."
    assert _coded(pt, 400, "PAGE_NOT_FAILED") == "Página 1 não está em status 'failed' (status atual: completed)"


def test_the_duplicate_and_queue_notes_follow_the_language():
    from shared.error_catalog import render

    for code, params in (("JOB_QUEUED", {}), ("TRANSCRIPTION_JOB_QUEUED", {}), ("JOB_DELETED", {}),
                         ("DUPLICATE_DOCUMENT", {"job_id": "j"}), ("DUPLICATE_AUDIO", {"job_id": "j"}),
                         ("DUPLICATE_NOTE_PURGED", {}), ("PAGE_RETRY_QUEUED", {"page_number": 2, "attempt": 1}),
                         ("REPROCESS_ORIGINAL_GONE", {"job_id": "j"}), ("NO_PROJECT", {})):
        assert render(code, lang="en", **params) != render(code, lang="pt", **params), code
    with use_lang("pt"):
        assert render("JOB_QUEUED") == "Job enfileirado para processamento"
    assert render("JOB_QUEUED") == "Job queued for processing"


# -- api keys ----------------------------------------------------------------------------


def test_api_key_create_with_project_and_project_id_is_coded(client):  # noqa: F811
    body = {"name": "k", "project": "A", "project_id": "proj-a"}
    en, pt = _both(lambda h: client(ALICE).post("/api-keys/", json=body, headers=h))
    assert _coded(en, 422, "LOCATION_PROJECT_AND_ID") == "Send either 'project' or 'project_id', not both."
    assert _coded(pt, 422, "LOCATION_PROJECT_AND_ID") == "Envie 'project' ou 'project_id', não os dois"


def test_api_key_name_error_keeps_its_code(client):  # noqa: F811
    body = {"name": "k", "project": "a\u0007b"}
    en, pt = _both(lambda h: client(ALICE).post("/api-keys/", json=body, headers=h))
    assert _coded(en, 422, "PROJECT_NAME_CONTROL_CHARS") == "The project name contains control characters."
    assert _coded(pt, 422, "PROJECT_NAME_CONTROL_CHARS") == "Nome do projeto contém caracteres de controle"


def test_api_key_404_stays_text_but_localized(client):  # noqa: F811
    missing = str(uuid.uuid4())
    en = client(ALICE).delete(f"/api-keys/{missing}")
    pt = client(ALICE).delete(f"/api-keys/{missing}", headers=PT)
    assert (en.status_code, en.json()["detail"]) == (404, "API key not found")
    assert (pt.status_code, pt.json()["detail"]) == (404, "API key não encontrada")
    foreign = client(BOB).delete(f"/api-keys/{KEY_A}", headers=PT)
    assert foreign.json() == pt.json()


# -- authentication ----------------------------------------------------------------------


@pytest.fixture
def auth_client():
    app = FastAPI()

    @app.get("/whoami")
    def whoami(user=Depends(get_current_user)):
        return {"id": user.id}

    app.add_middleware(LanguageMiddleware)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_401_is_coded_localized_and_keeps_www_authenticate(auth_client):
    en = auth_client.get("/whoami")
    pt = auth_client.get("/whoami", headers=PT)
    assert _coded(en, 401, "NOT_AUTHENTICATED") == "Could not validate credentials"
    assert _coded(pt, 401, "NOT_AUTHENTICATED") == "Não foi possível validar as credenciais"
    assert en.headers["www-authenticate"] == pt.headers["www-authenticate"] == "Bearer"


def _login(username, password):
    return asyncio.run(auth_routes.login(request(), username=username, password=password, db=None))


def test_login_failure_is_coded_in_both_languages_and_keeps_www_authenticate(redis, credentials):  # noqa: F811
    for lang, text in (("en", "Incorrect username/email or password"),
                       ("pt", "Usuário/e-mail ou senha incorretos")):
        with use_lang(lang), pytest.raises(HTTPException) as exc:
            _login("alice", "wrong")
        assert exc.value.status_code == 401
        assert exc.value.detail == {"code": "INVALID_CREDENTIALS", "message": text}
        assert exc.value.headers == {"WWW-Authenticate": "Bearer"}
        rate_limit.reset("login:failed", "user:user-1")


def test_login_lockout_429_is_coded_and_keeps_retry_after(redis, credentials):  # noqa: F811
    for _ in range(3):
        with pytest.raises(HTTPException):
            _login("alice", "wrong")
    for lang, text in (("en", "Too many login attempts. Try again later."),
                       ("pt", "Muitas tentativas de login. Tente novamente mais tarde.")):
        with use_lang(lang), pytest.raises(HTTPException) as exc:
            _login("alice", "right")
        assert exc.value.status_code == 429
        assert exc.value.detail == {"code": "LOGIN_RATE_LIMITED", "message": text}
        assert int(exc.value.headers["Retry-After"]) > 0


def test_ip_rate_limit_429_is_coded_and_keeps_retry_after(redis):  # noqa: F811
    rate_limit.hit("t:ip", "198.51.100.9", 1, 60)
    for lang, text in (("en", "Too many attempts. Try again later."),
                       ("pt", "Muitas tentativas. Tente novamente mais tarde.")):
        with use_lang(lang), pytest.raises(HTTPException) as exc:
            rate_limit.hit("t:ip", "198.51.100.9", 1, 60)
        assert exc.value.status_code == 429
        assert exc.value.detail == {"code": "REQUEST_RATE_LIMITED", "message": text}
        assert exc.value.headers["Retry-After"] == "60"


def test_inactive_user_is_coded_in_both_languages():
    import shared.auth as auth

    inactive = SimpleNamespace(is_active=False)
    for lang, text in (("en", "Inactive user account"), ("pt", "Conta de usuário inativa")):
        with use_lang(lang), pytest.raises(HTTPException) as exc:
            asyncio.run(auth.get_current_active_user(inactive))
        assert exc.value.status_code == 400
        assert exc.value.detail == {"code": "USER_INACTIVE", "message": text}


def test_register_with_a_taken_email_is_coded_in_both_languages_and_creates_nothing(db):  # noqa: F811
    from shared.models import User
    from shared.schemas import UserCreate

    before = db.query(User).count()
    data = UserCreate(email="a@example.com", username="newname", password="Str0ng!Passw0rd")
    for lang, text in (("en", "Email already registered"), ("pt", "E-mail já cadastrado")):
        with use_lang(lang), pytest.raises(HTTPException) as exc:
            asyncio.run(auth_routes.register(data, request(), db=db))
        assert exc.value.status_code == 400
        assert exc.value.detail == {"code": "EMAIL_ALREADY_REGISTERED", "message": text}
    assert db.query(User).count() == before
