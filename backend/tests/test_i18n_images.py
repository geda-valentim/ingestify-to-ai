"""Datalake and /images refusals answer in the request language (P-13 slice 3).

`/images` keeps its `{"detail": {"error_code", "message", "job_id"}}` envelope;
only `message` follows Accept-Language. The datalake routes answer `{"code",
"message"}` (the 404 non-disclosure texts stay text, localized).
"""

import base64
import re
from pathlib import Path

import pytest

from api import image_routes
from shared import error_catalog
from shared.i18n import LanguageMiddleware, use_lang
from tests.test_upload_projects import db, env, jwt  # noqa: F401
from tests.test_upload_projects import projects_module

PT = {"Accept-Language": "pt-BR"}


@pytest.fixture
def i18n_env(env):  # noqa: F811
    env.client.app.add_middleware(LanguageMiddleware)
    return env


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _describe(env, image_base64, **headers):
    return env.client.post(
        "/images/describe",
        headers={**jwt(), **headers},
        json={"image_base64": image_base64, "project": "P"},
    )


def _detail(response):
    return response.json()["detail"]


# --- /images envelope ---------------------------------------------------------------------


def test_invalid_base64_keeps_the_envelope_and_localizes_the_message(i18n_env):
    default = _describe(i18n_env, "")
    portuguese = _describe(i18n_env, "", **PT)
    assert default.status_code == portuguese.status_code == 422
    for response in (default, portuguese):
        assert set(_detail(response)) == {"error_code", "message", "job_id"}
        assert _detail(response)["error_code"] == "INVALID_BASE64"
        assert _detail(response)["job_id"] is None
    assert _detail(default)["message"].startswith("image_base64 is empty.")
    assert _detail(portuguese)["message"].startswith("image_base64 está vazio.")


def test_unsupported_format_and_oversize_render_with_their_params(i18n_env, monkeypatch):
    png_less = _b64(b"not an image at all")
    default = _describe(i18n_env, png_less)
    portuguese = _describe(i18n_env, png_less, **PT)
    assert default.status_code == portuguese.status_code == 422
    assert _detail(default)["error_code"] == _detail(portuguese)["error_code"] == "UNSUPPORTED_IMAGE_FORMAT"
    assert "Unsupported image format. Accepted formats: image/png" in _detail(default)["message"]
    assert "Formato de imagem não suportado. Formatos aceitos: image/png" in _detail(portuguese)["message"]

    monkeypatch.setattr(image_routes.settings, "vision_max_image_size_mb", 0)
    default = _describe(i18n_env, png_less)
    portuguese = _describe(i18n_env, png_less, **PT)
    assert default.status_code == portuguese.status_code == 413
    assert _detail(default)["error_code"] == _detail(portuguese)["error_code"] == "IMAGE_TOO_LARGE"
    assert "over the 0MB limit" in _detail(default)["message"]
    assert "acima do limite de 0MB" in _detail(portuguese)["message"]


def test_vision_disabled_is_one_code_in_two_languages(i18n_env, monkeypatch):
    monkeypatch.setattr(image_routes.settings, "enable_image_description", False)
    default = _describe(i18n_env, "x")
    portuguese = _describe(i18n_env, "x", **PT)
    assert default.status_code == portuguese.status_code == 503
    assert _detail(default)["error_code"] == _detail(portuguese)["error_code"] == "VISION_DISABLED"
    assert _detail(default)["message"].startswith("Image description is currently disabled")
    assert _detail(portuguese)["message"].startswith("A descrição de imagens está desativada")


def test_folder_limit_through_images_has_error_code_and_portuguese_message(i18n_env, monkeypatch):
    monkeypatch.setattr(projects_module.get_settings(), "max_folders_per_project", 1)
    from tests.test_upload_projects import post

    assert post(i18n_env, "/images/describe/upload", {"project": "P", "folder": "link-1"}).status_code == 200
    default = post(i18n_env, "/images/describe/upload", {"project": "P", "folder": "link-2"})
    portuguese = post(
        i18n_env, "/images/describe/upload", {"project": "P", "folder": "link-3"}, headers={**jwt(), **PT}
    )
    assert default.status_code == portuguese.status_code == 422
    assert _detail(default) == {
        "error_code": "FOLDER_LIMIT",
        "message": "The limit of 1 folders in this project has been reached.",
        "job_id": None,
    }
    assert _detail(portuguese)["error_code"] == "FOLDER_LIMIT"
    assert _detail(portuguese)["job_id"] is None
    assert _detail(portuguese)["message"] == "Limite de 1 pastas atingido neste projeto"


def test_capabilities_reason_and_the_full_analysis_404_follow_the_language():
    with use_lang("en"):
        assert image_routes.no_vision_worker_reason().startswith("no vision worker heartbeat in the last")
        english_404 = image_routes.full_analysis_not_found_detail()
    with use_lang("pt"):
        assert image_routes.no_vision_worker_reason().startswith("nenhum heartbeat do worker de visão")
        assert image_routes.full_analysis_not_found_detail() == "Full Analysis não encontrada"
    assert english_404 == "Full Analysis not found"


# --- catalog hygiene for the files of this slice ---------------------------------------------

_BACKEND = Path(__file__).resolve().parents[1]
_USED = re.compile(
    r"""(?:api_error|_error|render|DatalakeError|PartitionError)\(\s*(?:\d+,\s*)?["']([A-Z][A-Z0-9_]+)["']"""
    r"""|key=["']([A-Z][A-Z0-9_]+)["']|catalog_code=["']([A-Z][A-Z0-9_]+)["']"""
)


def test_every_code_this_slice_raises_is_bilingual():
    files = [
        "api/datalake_routes.py", "api/image_routes.py", "api/image_full_routes.py", "api/face_routes.py",
        "workers/vision/image_input.py",
        *[str(p.relative_to(_BACKEND)) for p in (_BACKEND / "shared/datalake").glob("*.py")],
    ]
    used = set()
    for rel in files:
        for groups in _USED.findall((_BACKEND / rel).read_text()):
            used |= {g for g in groups if g}
    assert len(used) > 60
    missing = sorted(c for c in used if c not in error_catalog.CATALOG)
    assert not missing, missing
    assert not [c for c in used if "en" not in error_catalog.CATALOG[c][0]]
