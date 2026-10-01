"""
The upload contract of spec 0003 (§ 4.4), on all seven endpoints that create
a job: the project is mandatory (request, else the API key's bound project,
else 422), names are get-or-add, IDs are owned-or-404, deduplication is
scoped by project.

Authentication is the real one (JWT and X-API-Key through shared/auth.py), so
"JWT wins over the key" and the production client's exact request are tested
end to end. Below the API everything is faked: SQLite (foreign keys ON), fake
Redis, fake MinIO, Celery and the vision worker replaced by recorders.
"""
import base64
import itertools
import logging
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import image_routes, routes
from api.projects_api import PROJECT_REQUIRED_DETAIL
from shared import projects as projects_module
from shared.auth import create_access_token, hash_api_key
from shared.database import Base, get_db
from shared.models import APIKey, Folder, Job, JobStatus, Project, User
from workers import tasks

ALICE = "user-alice"
BOB = "user-bob"
INBOX_KEY_PLAIN = "doc2md_sk_inbox-bound-key"
UNBOUND_KEY_PLAIN = "doc2md_sk_unbound-key"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
VISION_PAYLOAD = {
    "ok": True, "description": "um pixel", "task": "<MORE_DETAILED_CAPTION>", "text": "",
    "lines": [], "width": 1, "height": 1, "duration_ms": 1,
    "model": {"model_id": "m", "revision": "r", "device": "cpu", "dtype": "float32"},
}
_counter = itertools.count()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        User(id=ALICE, email="alice@example.com", username="alice", hashed_password="x"),
        User(id=BOB, email="bob@example.com", username="bob", hashed_password="x"),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()


class FakeMinio:
    bucket_uploads = "ingestify-uploads"
    bucket_audio = "ingestify-audio"

    def upload_file(self, **kwargs):
        pass


class FakeAsyncResult:
    def ready(self):
        return True

    result = VISION_PAYLOAD


@pytest.fixture
def env(db, fake_redis, tmp_path, monkeypatch):
    enqueued = []
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(routes.settings, "enable_audio_transcription", True)
    monkeypatch.setattr(image_routes.settings, "enable_image_description", True)
    monkeypatch.setattr(projects_module.get_settings(), "upload_fallback_project", "")
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(image_routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(routes, "get_minio_client", lambda: FakeMinio())
    monkeypatch.setattr(tasks.process_conversion, "delay", lambda **kw: enqueued.append(kw))
    monkeypatch.setattr(tasks.process_conversion, "apply_async", lambda **kw: enqueued.append(kw))
    monkeypatch.setattr(image_routes, "_dispatch_vision_task",
                        lambda kind, **kw: enqueued.append(kw) or FakeAsyncResult())

    app = FastAPI()
    app.include_router(image_routes.router)
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    return SimpleNamespace(client=TestClient(app), db=db, tmp=tmp_path, enqueued=enqueued)


def add_project(db, user_id, name, key=None):
    project = Project(user_id=user_id, name=name, name_key=key or projects_module.name_key(name))
    db.add(project)
    db.commit()
    return project


def add_folder(db, project, name):
    folder = Folder(project_id=project.id, user_id=project.user_id, name=name,
                    name_key=projects_module.name_key(name))
    db.add(folder)
    db.commit()
    return folder


def add_key(db, plain, user_id=ALICE, project=None, name="key"):
    key = APIKey(user_id=user_id, key_hash=hash_api_key(plain), name=name,
                 project_id=project.id if project else None)
    db.add(key)
    db.commit()
    return key


def jwt(user_id=ALICE):
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


def api_key(plain):
    return {"X-API-Key": plain}


# ---------------------------------------------------------------------------
# The seven endpoints
# ---------------------------------------------------------------------------

def _unique(prefix: bytes) -> bytes:
    return prefix + f"-{next(_counter)}".encode()


def _form(endpoint, fields, content):
    if endpoint == "/upload":
        return {"files": {"file": ("doc.pdf", content or _unique(b"%PDF-1.4"), "application/pdf")}, "data": fields}
    if endpoint == "/convert":
        return {"files": {"file": ("doc.pdf", content or _unique(b"%PDF-1.4"), "application/pdf")},
                "data": {"source_type": "file", **fields}}
    if endpoint == "/transcribe":
        return {"files": {"file": ("talk.mp3", content or _unique(b"ID3audio"), "audio/mpeg")}, "data": fields}
    if endpoint.endswith("/upload"):  # /images/*/upload
        return {"files": {"file": ("foto.png", content or _unique(PNG), "image/png")}, "data": fields}
    # JSON image endpoints
    return {"json": {"image_base64": base64.b64encode(content or _unique(PNG)).decode(), **fields}}


ENDPOINTS = [
    "/upload", "/convert", "/transcribe",
    "/images/describe", "/images/describe/upload", "/images/ocr", "/images/ocr/upload",
]
DEDUP_ENDPOINTS = ["/upload", "/convert", "/transcribe"]


def post(env, endpoint, fields=None, headers=None, content=None):
    return env.client.post(endpoint, headers=headers if headers is not None else jwt(),
                           **_form(endpoint, fields or {}, content))


def message(response):
    detail = response.json()["detail"]
    return detail["message"] if isinstance(detail, dict) else detail


def job_of(env, response):
    return env.db.get(Job, str(response.json()["job_id"]))


def files_on_disk(env):
    return [p for p in env.tmp.rglob("*") if p.is_file()]


# ---------------------------------------------------------------------------
# Mandatory project
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_jwt_without_project_is_422_and_nothing_is_written(env, endpoint):
    response = post(env, endpoint)
    assert response.status_code == 422
    assert message(response) == PROJECT_REQUIRED_DETAIL
    assert env.db.query(Job).count() == 0
    assert env.db.query(Project).count() == 0
    assert files_on_disk(env) == []
    assert env.enqueued == []


def test_required_message_has_the_curl_example():
    assert "-F \"project=Aulas\"" in PROJECT_REQUIRED_DETAIL
    assert "vincule a API key a um projeto em /api-keys" in PROJECT_REQUIRED_DETAIL


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_empty_field_counts_as_absent(env, endpoint):
    response = post(env, endpoint, {"project": "  ", "project_id": ""})
    assert response.status_code == 422
    assert message(response) == PROJECT_REQUIRED_DETAIL


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_bound_key_without_project_uses_the_keys_project(env, endpoint):
    bound = add_project(env.db, ALICE, "Transcrições")
    add_key(env.db, INBOX_KEY_PLAIN, project=bound)

    response = post(env, endpoint, headers=api_key(INBOX_KEY_PLAIN))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"] == {"id": bound.id, "name": "Transcrições", "created": False, "source": "api_key"}
    assert body["folder"] is None
    assert job_of(env, response).project_id == bound.id


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_explicit_project_wins_over_the_key(env, endpoint):
    bound = add_project(env.db, ALICE, "Transcrições")
    add_key(env.db, INBOX_KEY_PLAIN, project=bound)

    response = post(env, endpoint, {"project": "Cliente X"}, headers=api_key(INBOX_KEY_PLAIN))
    assert response.status_code == 200, response.text
    assert response.json()["project"]["name"] == "Cliente X"
    assert response.json()["project"]["source"] == "request"
    assert job_of(env, response).project_id != bound.id


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_jwt_and_key_together_is_a_jwt_request(env, endpoint):
    bound = add_project(env.db, ALICE, "Transcrições")
    add_key(env.db, INBOX_KEY_PLAIN, project=bound)

    response = post(env, endpoint, headers={**jwt(), **api_key(INBOX_KEY_PLAIN)})
    assert response.status_code == 422
    assert message(response) == PROJECT_REQUIRED_DETAIL


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_unbound_key_without_project_is_422(env, endpoint):
    add_key(env.db, UNBOUND_KEY_PLAIN)
    response = post(env, endpoint, headers=api_key(UNBOUND_KEY_PLAIN))
    assert response.status_code == 422
    assert message(response) == PROJECT_REQUIRED_DETAIL


def test_key_bound_to_a_vanished_project_is_422(env):
    gone = add_project(env.db, ALICE, "Apagado")
    add_key(env.db, INBOX_KEY_PLAIN, project=gone)
    env.db.delete(gone)
    env.db.commit()

    response = post(env, "/transcribe", headers=api_key(INBOX_KEY_PLAIN))
    assert response.status_code == 422
    assert "projeto vinculado a esta API key não existe mais" in message(response)


def test_key_bound_to_someone_elses_project_is_not_used(env):
    theirs = add_project(env.db, BOB, "Do Bob")
    add_key(env.db, INBOX_KEY_PLAIN, project=theirs)  # alice's key, bob's project (never valid)

    response = post(env, "/upload", headers=api_key(INBOX_KEY_PLAIN))
    assert response.status_code == 422
    assert env.db.query(Job).count() == 0


# ---------------------------------------------------------------------------
# Get-or-add and IDs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_new_name_is_created_and_equivalent_spelling_reuses_it(env, endpoint):
    first = post(env, endpoint, {"project": "Reunião Semanal", "folder": "Áudios"})
    assert first.status_code == 200, first.text
    assert first.json()["project"]["created"] is True
    assert first.json()["folder"]["created"] is True

    second = post(env, endpoint, {"project": "  reuniao   SEMANAL ", "folder": "audios"})
    assert second.status_code == 200, second.text
    assert second.json()["project"] == {**first.json()["project"], "created": False}
    assert second.json()["folder"] == {**first.json()["folder"], "created": False}
    assert env.db.query(Project).count() == 1
    assert env.db.query(Folder).count() == 1

    job = job_of(env, second)
    assert (job.project_id, job.folder_id) == (first.json()["project"]["id"], first.json()["folder"]["id"])


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_ids_select_existing_project_and_folder(env, endpoint):
    project = add_project(env.db, ALICE, "Cliente X")
    folder = add_folder(env.db, project, "Contratos")

    response = post(env, endpoint, {"project_id": project.id, "folder_id": folder.id})
    assert response.status_code == 200, response.text
    assert response.json()["project"]["id"] == project.id
    assert response.json()["folder"] == {"id": folder.id, "name": "Contratos", "created": False}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_foreign_or_unknown_project_id_is_the_same_404(env, endpoint):
    theirs = add_project(env.db, BOB, "Do Bob")
    foreign = post(env, endpoint, {"project_id": theirs.id})
    unknown = post(env, endpoint, {"project_id": "00000000-0000-4000-8000-000000000000"})
    assert foreign.status_code == unknown.status_code == 404
    assert message(foreign) == message(unknown) == "Projeto não encontrado"
    assert env.db.query(Job).count() == 0
    assert files_on_disk(env) == []


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_foreign_folder_id_is_404(env, endpoint):
    mine = add_project(env.db, ALICE, "Meu")
    theirs = add_folder(env.db, add_project(env.db, BOB, "Do Bob"), "Pasta do Bob")
    response = post(env, endpoint, {"project_id": mine.id, "folder_id": theirs.id})
    assert response.status_code == 404
    assert message(response) == "Pasta não encontrada"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_folder_of_another_project_is_422(env, endpoint):
    a = add_project(env.db, ALICE, "A")
    b_folder = add_folder(env.db, add_project(env.db, ALICE, "B"), "Pasta de B")
    response = post(env, endpoint, {"project_id": a.id, "folder_id": b_folder.id})
    assert response.status_code == 422
    assert env.db.query(Job).count() == 0


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("fields", [
    {"project": "X", "project_id": "00000000-0000-4000-8000-000000000000"},   # name and id
    {"project": "X", "folder": "F", "folder_id": "00000000-0000-4000-8000-000000000000"},
    {"folder": "Sem projeto"},                                                 # folder without project
    {"project": "X", "folder": "Contratos/2026"},                             # '/' in a folder
    {"project": "x" * 101},                                                   # too long
    {"project": "ﬃ" * 100},                                              # key > 200
    {"project": "a\x07b"},                                                    # control character
])
def test_invalid_location_is_422_and_creates_nothing(env, endpoint, fields):
    response = post(env, endpoint, fields)
    assert response.status_code == 422, response.text
    assert env.db.query(Project).count() == 0
    assert env.db.query(Job).count() == 0
    assert files_on_disk(env) == []


def test_project_limit_is_422(env, monkeypatch):
    monkeypatch.setattr(projects_module.get_settings(), "max_projects_per_user", 1)
    assert post(env, "/upload", {"project": "Um"}).status_code == 200
    response = post(env, "/upload", {"project": "Dois"})
    assert response.status_code == 422
    assert message(response) == "Limite de 1 projetos atingido"
    assert not [p for p in files_on_disk(env) if ".staging" in str(p)]  # staged upload removed


def test_fallback_project_valve(env, monkeypatch, caplog):
    monkeypatch.setattr(projects_module.get_settings(), "upload_fallback_project", "Sem Projeto")
    with caplog.at_level(logging.WARNING, logger="api.projects_api"):
        response = post(env, "/upload")
    assert response.status_code == 200, response.text
    assert response.json()["project"]["name"] == "Sem Projeto"
    assert response.json()["project"]["source"] == "fallback"
    assert any("UPLOAD_FALLBACK_PROJECT used" in r.message and ALICE in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Deduplication, scoped by project
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint", DEDUP_ENDPOINTS)
def test_same_file_same_project_returns_the_existing_job(env, endpoint):
    content = _unique(b"%PDF-same" if endpoint != "/transcribe" else b"ID3same")
    first = post(env, endpoint, {"project": "A", "folder": "F1"}, content=content)
    again = post(env, endpoint, {"project": "a", "folder": "F2"}, content=content)
    assert again.status_code == 200
    assert again.json()["job_id"] == first.json()["job_id"]
    # not moved (D5): the response tells where the job really is
    assert again.json()["folder"]["name"] == "F1"
    assert env.db.query(Job).count() == 1


@pytest.mark.parametrize("endpoint", DEDUP_ENDPOINTS)
def test_same_file_other_project_is_processed_again(env, endpoint):
    content = _unique(b"%PDF-same" if endpoint != "/transcribe" else b"ID3same")
    first = post(env, endpoint, {"project": "Cliente A"}, content=content)
    second = post(env, endpoint, {"project": "Cliente B"}, content=content)
    assert second.status_code == 200
    assert second.json()["job_id"] != first.json()["job_id"]
    assert second.json()["message"] == (
        f"Arquivo já processado no projeto 'Cliente A' (job {first.json()['job_id']}); "
        f"processando de novo em 'Cliente B'"
    )
    assert env.db.query(Job).count() == 2


def test_convert_does_not_dedup_a_failed_job(env):
    content = _unique(b"%PDF-failed")
    first = post(env, "/convert", {"project": "A"}, content=content)
    job = job_of(env, first)
    job.status = JobStatus.FAILED
    env.db.commit()

    again = post(env, "/convert", {"project": "A"}, content=content)
    assert again.json()["job_id"] != first.json()["job_id"]


# ---------------------------------------------------------------------------
# The production client, after the migration
# ---------------------------------------------------------------------------

def test_production_client_request_is_unchanged(env):
    """
    Today's exact request (file + output_format=json + purge_source=true +
    X-API-Key, no project) after the migration bound the key to Inbox: same
    status and fields as before (+ project/folder), and the job already
    processed in Inbox is still found by deduplication.
    """
    inbox = add_project(env.db, ALICE, "Inbox", key="inbox")
    add_key(env.db, INBOX_KEY_PLAIN, project=inbox, name="cliente-audio")
    audio = b"ID3-the-same-recording"
    legacy = Job(id="11111111-1111-4111-8111-111111111111", user_id=ALICE, job_type="MAIN",
                 source_type="audio", filename="rec.mp3", name="rec.mp3",
                 file_checksum=__import__("hashlib").sha256(audio).hexdigest(),
                 status=JobStatus.COMPLETED, created_at=datetime(2026, 9, 30, 8, 0, 0),
                 project_id=inbox.id)
    env.db.add(legacy)
    env.db.commit()

    def production_request(content):
        return env.client.post(
            "/transcribe",
            headers={"X-API-Key": INBOX_KEY_PLAIN},
            files={"file": ("rec.mp3", content, "audio/mpeg")},
            data={"output_format": "json", "purge_source": "true"},
        )

    repeated = production_request(audio)
    assert repeated.status_code == 200
    assert repeated.json() == {
        "job_id": legacy.id,
        "status": "queued",
        "created_at": "2026-09-30T08:00:00",
        "message": f"Arquivo de áudio já foi processado anteriormente (job existente: {legacy.id})",
        "project": {"id": inbox.id, "name": "Inbox", "created": False, "source": "api_key"},
        "folder": None,
    }

    new = production_request(b"ID3-a-new-recording")
    assert new.status_code == 200
    body = new.json()
    assert set(body) == {"job_id", "status", "created_at", "message", "project", "folder"}
    assert body["status"] == "queued"
    assert body["message"] == "Job de transcrição de áudio enfileirado para processamento"
    assert job_of(env, new).project_id == inbox.id
    options = env.enqueued[-1]["kwargs"]["options"]
    assert options["output_format"] == "json" and options["purge_source"] is True
