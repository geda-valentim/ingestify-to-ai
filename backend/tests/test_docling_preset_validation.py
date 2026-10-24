"""An unknown docling_preset is refused with the 422 validation error on /upload and /convert,
before the file is stored or any job exists (it used to run silently with the server defaults)."""
import pytest

from shared.models import Job
from shared.schemas import DOCLING_PRESETS
from tests.test_upload_format import app_env  # noqa: F401
from tests.test_upload_projects import ALICE, FakeMinio, add_project, db, env, jwt  # noqa: F401

PDF = ("a.pdf", b"%PDF-1.4", "application/pdf")


def _post(env, endpoint, preset, **headers):
    data = {"project": "P", "docling_preset": preset}
    if endpoint == "/convert":
        data["source_type"] = "file"
    return env.client.post(endpoint, headers={**jwt(), **headers}, data=data, files={"file": PDF})


@pytest.fixture
def untouched(app_env, monkeypatch):
    """app_env that also records MinIO uploads."""
    uploads = []
    monkeypatch.setattr(FakeMinio, "upload_file", lambda self, **kw: uploads.append(kw))
    add_project(app_env.db, ALICE, "P")
    app_env.uploads = uploads
    return app_env


def test_valid_set_is_the_single_source():
    assert DOCLING_PRESETS == ("fast", "balanced", "quality")
    from workers.converter import _PRESET_FLAGS
    assert set(_PRESET_FLAGS) == set(DOCLING_PRESETS)


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
@pytest.mark.parametrize("preset", ["ultra", "FAST", "fast "])
def test_unknown_preset_is_422_and_leaves_nothing(untouched, endpoint, preset):
    response = _post(untouched, endpoint, preset)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["detail"][0]["loc"] == ["body", "docling_preset"]
    assert untouched.db.query(Job).count() == 0
    assert untouched.enqueued == []
    assert untouched.uploads == []
    assert [p for p in untouched.tmp.rglob("*") if p.is_file()] == []


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_refusal_is_the_same_in_english_and_portuguese(untouched, endpoint):
    english = _post(untouched, endpoint, "ultra")
    portuguese = _post(untouched, endpoint, "ultra", **{"Accept-Language": "pt-BR"})
    assert english.status_code == portuguese.status_code == 422
    assert english.json()["code"] == portuguese.json()["code"] == "VALIDATION_ERROR"
    assert english.json()["detail"] == portuguese.json()["detail"]


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
@pytest.mark.parametrize("preset", DOCLING_PRESETS)
def test_each_valid_preset_is_accepted(untouched, endpoint, preset):
    response = _post(untouched, endpoint, preset)
    assert response.status_code == 200, response.text
    assert untouched.enqueued[-1]["options"]["docling_preset"] == preset
    assert untouched.uploads


def test_empty_preset_means_omitted(untouched):
    upload = _post(untouched, "/upload", "")
    assert upload.status_code == 200, upload.text
    assert untouched.enqueued[-1]["options"]["docling_preset"] == "fast"
    convert = _post(untouched, "/convert", "")
    assert convert.status_code == 200, convert.text
    assert "docling_preset" not in (untouched.enqueued[-1].get("options") or {})
