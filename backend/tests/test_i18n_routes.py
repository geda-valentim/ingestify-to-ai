"""The job-creating routes answer in the request language (P-13 slice 1)."""

import pytest

from shared.i18n import LanguageMiddleware
from shared.models import Job
from tests.test_upload_projects import ALICE, add_project, db, env, jwt  # noqa: F401


@pytest.fixture
def i18n_env(env):  # noqa: F811
    env.client.app.add_middleware(LanguageMiddleware)
    return env


def _upload_empty(env, **headers):
    return env.client.post(
        "/upload",
        headers={**jwt(), **headers},
        data={"project": "P"},
        files={"file": ("a.pdf", b"", "application/pdf")},
    )


def test_empty_file_refusal_is_english_by_default_and_portuguese_on_request(i18n_env):
    """Same code and status; only `message` follows Accept-Language."""
    add_project(i18n_env.db, ALICE, "P")
    default = _upload_empty(i18n_env)
    portuguese = _upload_empty(i18n_env, **{"Accept-Language": "pt-BR"})
    assert default.status_code == portuguese.status_code == 400
    assert default.json()["detail"] == {"code": "FILE_EMPTY", "message": "The uploaded file is empty."}
    assert portuguese.json()["detail"] == {"code": "FILE_EMPTY", "message": "Arquivo enviado está vazio"}
    assert default.headers["content-language"] == "en"
    assert portuguese.headers["content-language"] == "pt-BR"
    assert i18n_env.db.query(Job).count() == 0


def test_project_required_is_a_location_error_in_both_languages(i18n_env):
    default = i18n_env.client.post(
        "/upload", headers=jwt(), files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}
    )
    portuguese = i18n_env.client.post(
        "/upload",
        headers={**jwt(), "Accept-Language": "pt"},
        files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert default.status_code == portuguese.status_code == 422
    assert default.json()["detail"]["code"] == portuguese.json()["detail"]["code"] == "PROJECT_REQUIRED"
    assert "Say which project" in default.json()["detail"]["message"]
    assert "Informe o projeto" in portuguese.json()["detail"]["message"]
