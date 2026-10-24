"""One envelope inside /images/*: {"detail": {"error_code", "message", "job_id"}} (P-13 slice 3)."""

import pytest

from api import image_routes
from shared.i18n import LanguageMiddleware, use_lang
from tests.test_upload_projects import db, env, jwt  # noqa: F401

PT = {"Accept-Language": "pt-BR"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def i18n_env(env):  # noqa: F811
    env.client.app.add_middleware(LanguageMiddleware)
    return env


def _detail(response):
    return response.json()["detail"]


def test_the_composite_message_gets_the_job_id():
    with use_lang("en"):
        message = image_routes._error(500, "VISION_INFERENCE_FAILED", "abc-1").detail["message"]
        assert "job abc-1 for the full error" in message
    with use_lang("pt"):
        message = image_routes._error(500, "VISION_INFERENCE_FAILED", "abc-1").detail["message"]
        assert "e o job abc-1 para o erro completo" in message


def test_the_merged_catalogs_do_not_overlap():
    """Bare asserts vanish under `python -O`: pin it here too."""
    from shared import catalog_api, catalog_images, error_catalog

    assert not set(catalog_api.API_CATALOG) & set(catalog_images.IMAGES_CATALOG)
    for table in (catalog_api.API_CATALOG, catalog_images.IMAGES_CATALOG):
        assert all(error_catalog.CATALOG[code] == table[code] for code in table)
    base = set(error_catalog.CATALOG) - set(catalog_api.API_CATALOG) - set(catalog_images.IMAGES_CATALOG)
    assert not base & (set(catalog_api.API_CATALOG) | set(catalog_images.IMAGES_CATALOG))


def _full(env, headers=None, **fields):
    return env.client.post(
        "/images/analyze/upload",
        headers={**jwt(), **(headers or {})},
        data={"project": "P", "mode": "full", **fields},
        files={"file": ("a.png", PNG, "image/png")},
    )


def _assert_envelope(default, portuguese, status, code):
    assert default.status_code == portuguese.status_code == status, (default.text, portuguese.text)
    for response in (default, portuguese):
        assert set(_detail(response)) == {"error_code", "message", "job_id"}
        assert _detail(response)["error_code"] == code
        assert _detail(response)["job_id"] is None
    assert _detail(default)["message"] != _detail(portuguese)["message"]


def test_full_analysis_refusals_keep_the_images_envelope(i18n_env):
    default = _full(i18n_env)
    portuguese = _full(i18n_env, PT)
    _assert_envelope(default, portuguese, 422, "IMAGE_IDEMPOTENCY_KEY_REQUIRED")
    assert "Idempotency-Key is required" in _detail(default)["message"]
    assert "Idempotency-Key é obrigatória" in _detail(portuguese)["message"]

    key = {"Idempotency-Key": "k-1"}
    body = {"datalake": '{"connection_id": "nope", "bucket": "bkt"}'}
    default = _full(i18n_env, key, **body)
    portuguese = _full(i18n_env, {**key, **PT}, **body)
    _assert_envelope(default, portuguese, 404, "DATALAKE_NOT_FOUND")
    assert _detail(default)["message"] == "Connection not found"
    assert _detail(portuguese)["message"] == "Conexão não encontrada"


def test_face_upload_refusals_keep_the_images_envelope(i18n_env):
    from api import face_routes

    i18n_env.client.app.include_router(face_routes.router)

    def upload(headers=None):
        return i18n_env.client.post(
            "/images/faces/upload",
            headers={**jwt(), "Idempotency-Key": "k-1", **(headers or {})},
            data={"project": "P", "bogus": "1"},
            files={"file": ("a.png", PNG, "image/png")},
        )

    _assert_envelope(upload(), upload(PT), 422, "FACE_UPLOAD_FIELDS_INVALID")
