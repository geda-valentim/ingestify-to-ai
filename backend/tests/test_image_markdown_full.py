"""`output_format=markdown` of the durable image routes: Full Analysis and faces.

output_format is not part of the Idempotency-Key fingerprint: a replay with
another output_format returns the same job, rendered in the requested format. The
default stored on the job (for GET /jobs/{id}/result) is the one of the request
that created it.
"""
import base64
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.database import get_db
from shared.models import Job, Project
from tests.test_face_analysis import Pipeline
from tests.test_image_full_analysis import memory, seed  # noqa: F401  (fixture)

MARKDOWN = "text/markdown; charset=utf-8"


@pytest.fixture
def world(memory, monkeypatch):
    from api import face_routes, image_full_routes, image_routes, routes
    from api.deps import get_current_active_user
    from workers import image_full_tasks
    from workers.vision import faces
    factory, storage, user = memory
    monkeypatch.setattr(image_full_routes, "get_minio_client", lambda: storage)
    monkeypatch.setattr(routes, "get_minio_client", lambda: storage)
    monkeypatch.setattr(image_full_tasks, "dispatch", lambda *args: None)
    from shared.face_analysis import manifest
    monkeypatch.setattr(face_routes, "require_faces", lambda mode: {"models": manifest()["models"]})
    monkeypatch.setattr(faces, "FacePipeline", Pipeline)
    monkeypatch.setattr(image_routes.settings, "enable_image_description", True)
    app = FastAPI()
    for module in (face_routes, image_routes, routes):
        app.include_router(module.router)

    def db_dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_active_user] = lambda: user
    with factory() as db:
        project = Project(id=str(uuid4()), user_id=user.id, name="md", name_key="md")
        db.add(project)
        db.commit()
    temporary = seed(memory)
    raw = storage.objects[f"images/{temporary}/source"]

    class World:
        pass
    w = World()
    w.client, w.factory, w.storage, w.raw, w.project = TestClient(app), factory, storage, raw, project.id
    w.body = {"image_base64": base64.b64encode(raw).decode(), "filename": "grupo.png", "project_id": project.id}
    return w


def _run(job_id):
    from workers.image_full_tasks import run_full_image_task
    run_full_image_task.run(job_id=job_id)


def _options(world, job_id):
    with world.factory() as db:
        return dict(db.get(Job, job_id).configuration_row.options)


def test_faces_markdown_replay_result_default_and_formats(world):
    key = {"Idempotency-Key": "faces-md"}
    created = world.client.post("/images/faces", json={**world.body, "output_format": "markdown"}, headers=key)
    assert created.status_code == 202 and created.headers["content-type"] == "application/json"
    job_id = created.json()["job_id"]
    assert _options(world, job_id)["output_format"] == "markdown"
    _run(job_id)

    # Replays: same job whatever output_format, rendered as asked
    as_md = world.client.post("/images/faces", json={**world.body, "output_format": "markdown", "wait": True},
                              headers=key)
    assert as_md.status_code == 200 and as_md.headers["content-type"] == MARKDOWN
    text = as_md.text
    assert text.startswith("# Análise facial da imagem\n\n- Estado da análise: `completed`")
    assert "| `face-001` | 1 | 2 | 20 | 22 | 0.9000 |" in text and "(não calibrados)" in text
    assert f"- Job: `{job_id}`" in text and "- Arquivo: grupo.png" in text
    assert "- Modelos: `blaze_face_short_range`" in text
    as_json = world.client.post("/images/faces", json={**world.body, "wait": True}, headers=key)
    assert as_json.status_code == 202 and as_json.json()["job_id"] == job_id
    assert as_json.json()["image"]["operation"] == "face_analysis"
    multipart = world.client.post("/images/faces/upload", headers=key,
                                  data={"project_id": world.project, "wait": "true", "output_format": "markdown"},
                                  files={"file": ("grupo.png", world.raw)})
    assert multipart.status_code == 200, multipart.text
    assert multipart.headers["content-type"] == MARKDOWN and multipart.text == text
    with world.factory() as db:
        assert db.query(Job).filter(Job.source_type == "image", Job.id != job_id).count() == 1  # the seed only

    # GET /jobs/{id}/result: stored default is markdown; ?format=json is the report
    default = world.client.get(f"/jobs/{job_id}/result")
    assert default.headers["content-type"] == MARKDOWN and default.text == text
    report = world.client.get(f"/jobs/{job_id}/result?format=json")
    assert report.headers["content-type"] == "application/json"
    assert report.json()["image"]["operation"] == "face_analysis"
    bad = world.client.get(f"/jobs/{job_id}/result?format=srt")
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "IMAGE_RESULT_FORMAT_UNSUPPORTED"
    assert "análise facial" in bad.json()["detail"]["message"]


def test_faces_default_json_is_unchanged_and_markdown_on_demand(world):
    key = {"Idempotency-Key": "faces-json"}
    created = world.client.post("/images/faces", json=world.body, headers=key)
    job_id = created.json()["job_id"]
    assert "output_format" not in _options(world, job_id)
    _run(job_id)
    default = world.client.get(f"/jobs/{job_id}/result")
    assert default.headers["content-type"] == "application/json"
    assert default.json()["result"]["image"]["operation"] == "face_analysis"
    rendered = world.client.get(f"/jobs/{job_id}/result?format=markdown")
    assert rendered.headers["content-type"] == MARKDOWN
    assert rendered.text.startswith("# Análise facial da imagem")
    replay = world.client.post("/images/faces", json={**world.body, "wait": True}, headers=key)
    assert replay.status_code == 202 and set(replay.json()) == {"job_id", "status", "markdown", "image", "attempt"}


def test_full_markdown_json_and_multipart(world):
    key = {"Idempotency-Key": "full-md"}
    body = {**world.body, "mode": "full", "output_format": "markdown"}
    created = world.client.post("/images/analyze", json=body, headers=key)
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]
    assert _options(world, job_id)["output_format"] == "markdown"
    _run(job_id)
    rendered = world.client.post("/images/analyze", json={**body, "wait": True}, headers=key)
    assert rendered.status_code == 200 and rendered.headers["content-type"] == MARKDOWN
    text = rendered.text
    assert text.startswith("# Análise completa da imagem\n\n- Estado da análise: ")
    for section in ("## Descrição", "## Texto (OCR)", "## Detecções", "## Resultados por tarefa", "## Metadados"):
        assert section in text
    multipart = world.client.post("/images/analyze/upload", headers=key, files={"file": ("grupo.png", world.raw)},
                                  data={"mode": "full", "project_id": world.project, "wait": "true",
                                        "output_format": "json"})
    assert multipart.status_code == 200 and multipart.json()["job_id"] == job_id
    assert multipart.json()["image"]["operation"] == "full_analysis"
    assert world.client.get(f"/jobs/{job_id}/result").text == text
    raw = world.client.get(f"/jobs/{job_id}/result?format=json")
    assert raw.json()["image"]["coverage"]["task_families_total"] == 15


@pytest.mark.parametrize("path,kind", [("/images/faces", "json"), ("/images/faces/upload", "multipart"),
                                       ("/images/analyze", "json"), ("/images/analyze/upload", "multipart")])
def test_invalid_output_format_is_422(world, path, kind):
    headers = {"Idempotency-Key": f"bad-{path}"}
    if kind == "json":
        body = {**world.body, "output_format": "html"}
        if "analyze" in path:
            body["mode"] = "full"
        response = world.client.post(path, json=body, headers=headers)
    else:
        data = {"project_id": world.project, "output_format": "html"}
        if "analyze" in path:
            data["mode"] = "full"
        response = world.client.post(path, data=data, files={"file": ("grupo.png", world.raw)}, headers=headers)
    assert response.status_code == 422
    with world.factory() as db:
        assert db.query(Job).count() == 1  # the seed only
