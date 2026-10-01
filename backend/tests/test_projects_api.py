"""
Read API of spec 0003 (§ 4.6, phase 1): GET /projects, the resolve endpoints,
the project/folder filters and fields of GET /jobs and GET /jobs/{id}, and the
API-key binding (GET/POST/PATCH /api-keys).
"""
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import apikey_routes, projects_api, routes, tag_routes
from shared.auth import get_current_active_user
from shared.database import Base, get_db
from shared.models import APIKey, Folder, Job, JobStatus, Project, User
from shared.projects import name_key
from shared.tags import set_job_tags

ALICE = "user-alice"
BOB = "user-bob"


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


@pytest.fixture
def client(db, fake_redis, monkeypatch):
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("api.deps._redis_owner_matches", lambda job_id, user_id: False)
    monkeypatch.setattr("api.deps._redis_job_status", lambda job_id: None)
    app = FastAPI()
    app.include_router(apikey_routes.router, prefix="/api-keys")
    app.include_router(projects_api.router)
    app.include_router(tag_routes.router)
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: db.get(User, ALICE)
    return TestClient(app)


def project(db, name, user_id=ALICE, archived=False):
    p = Project(user_id=user_id, name=name, name_key=name_key(name),
                archived_at=datetime(2026, 1, 1) if archived else None)
    db.add(p)
    db.commit()
    return p


def folder(db, proj, name):
    f = Folder(project_id=proj.id, user_id=proj.user_id, name=name, name_key=name_key(name))
    db.add(f)
    db.commit()
    return f


def job(db, job_id, proj=None, fold=None, user_id=ALICE, status=JobStatus.COMPLETED, day=1, tags=(),
        job_type="MAIN"):
    j = Job(id=job_id, user_id=user_id, name=job_id, filename=job_id, status=status, job_type=job_type,
            created_at=datetime(2026, 1, day), project_id=proj.id if proj else None,
            folder_id=fold.id if fold else None)
    db.add(j)
    set_job_tags(j, list(tags))
    db.commit()
    return j


def ids(response):
    assert response.status_code == 200, response.text
    return [j["job_id"] for j in response.json()["jobs"]]


# ---------------------------------------------------------------------------
# GET /projects
# ---------------------------------------------------------------------------

@pytest.fixture
def world(db):
    a = project(db, "Cliente A")
    b = project(db, "Beta")
    c = project(db, "Cia Vazia")
    a1 = folder(db, a, "Áudios")
    a2 = folder(db, a, "contratos")
    job(db, "a-root", a, day=2)
    job(db, "a1-ok", a, a1, day=3)
    job(db, "a1-failed", a, a1, status=JobStatus.FAILED, day=4)
    job(db, "a2-pending", a, a2, status=JobStatus.PENDING, day=5)
    job(db, "a-page", a, a1, job_type="PAGE", day=9)          # children never count
    job(db, "b-processing", b, status=JobStatus.PROCESSING, day=7)
    theirs = project(db, "Do Bob", user_id=BOB)
    job(db, "bob-job", theirs, user_id=BOB, day=8)
    db.add(APIKey(user_id=ALICE, key_hash="h1", name="cliente-audio", project_id=a.id))
    db.add(APIKey(user_id=ALICE, key_hash="h2", name="sem-projeto"))
    db.commit()
    return {"a": a, "b": b, "c": c, "a1": a1, "a2": a2, "theirs": theirs}


def test_list_projects_with_counts_and_folders(client, world):
    response = client.get("/projects", params={"include": "folders"})
    assert response.status_code == 200
    body = response.json()
    assert body["limits"] == {"max_projects": 200, "max_folders_per_project": 500}

    projects = body["projects"]
    assert [p["name"] for p in projects] == ["Beta", "Cliente A", "Cia Vazia"]  # last_job_at desc, then name
    a = projects[1]
    assert a == {
        "id": world["a"].id, "name": "Cliente A", "description": None, "archived": False,
        "job_count": 4, "root_job_count": 1, "failed_count": 1, "active_count": 1,
        "last_job_at": "2026-01-05T00:00:00",
        "api_keys": [{"id": a["api_keys"][0]["id"], "name": "cliente-audio"}],
        "folders": [
            {"id": world["a1"].id, "name": "Áudios", "job_count": 2},
            {"id": world["a2"].id, "name": "contratos", "job_count": 1},
        ],
    }
    assert projects[0]["active_count"] == 1
    empty = projects[2]
    assert (empty["job_count"], empty["last_job_at"], empty["folders"], empty["api_keys"]) == (0, None, [], [])


def test_list_projects_without_folders_omits_them(client, world):
    projects = client.get("/projects").json()["projects"]
    assert all("folders" not in p for p in projects)
    assert len(projects) == 3  # never another user's


def test_archived_flag(client, db):
    project(db, "Antigo", archived=True)
    assert client.get("/projects").json()["projects"][0]["archived"] is True


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------

def test_resolve_project_by_equivalent_spelling(client, db):
    p = project(db, "Reunião")
    assert client.get("/projects/resolve", params={"name": "  REUNIAO "}).json() == {
        "valid": True, "match": {"id": p.id, "name": "Reunião"}}


def test_resolve_project_that_would_be_created(client, db):
    project(db, "Reunião", user_id=BOB)  # someone else's never matches
    assert client.get("/projects/resolve", params={"name": "reuniao"}).json() == {"valid": True, "match": None}


@pytest.mark.parametrize("name,error", [
    ("x" * 101, "Nome muito longo (máximo 100 caracteres)"),
    ("   ", "Nome do projeto vazio"),
])
def test_resolve_invalid_project_name(client, name, error):
    assert client.get("/projects/resolve", params={"name": name}).json() == {"valid": False, "error": error}


def test_resolve_folder(client, db):
    p = project(db, "P")
    f = folder(db, p, "Áudios")
    url = f"/projects/{p.id}/folders/resolve"
    assert client.get(url, params={"name": "audios"}).json() == {"valid": True, "match": {"id": f.id, "name": "Áudios"}}
    assert client.get(url, params={"name": "novos"}).json() == {"valid": True, "match": None}
    assert client.get(url, params={"name": "a/b"}).json()["valid"] is False


def test_resolve_folder_of_someone_elses_project_is_404(client, db):
    theirs = project(db, "Do Bob", user_id=BOB)
    response = client.get(f"/projects/{theirs.id}/folders/resolve", params={"name": "x"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Projeto não encontrado"
    assert client.get("/projects/nope/folders/resolve", params={"name": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# GET /jobs filters and fields
# ---------------------------------------------------------------------------

def test_filter_by_project(client, world):
    assert ids(client.get("/jobs", params={"project_id": world["a"].id})) == [
        "a2-pending", "a1-failed", "a1-ok", "a-root"]


def test_filter_by_folder_and_root(client, world):
    a = world["a"].id
    assert ids(client.get("/jobs", params={"project_id": a, "folder_id": world["a1"].id})) == ["a1-failed", "a1-ok"]
    assert ids(client.get("/jobs", params={"project_id": a, "folder_id": "root"})) == ["a-root"]
    # folder without project: the project is the folder's
    assert ids(client.get("/jobs", params={"folder_id": world["a2"].id})) == ["a2-pending"]


def test_location_filters_combine_with_status_and_tags(client, db, world):
    job(db, "a-tagged", world["a"], world["a1"], tags=["nf"], day=6)
    job(db, "b-tagged", world["b"], tags=["nf"], day=6)
    params = {"project_id": world["a"].id, "tag": "nf"}
    assert ids(client.get("/jobs", params=params)) == ["a-tagged"]
    body = client.get("/jobs", params={"project_id": world["a"].id, "status": "failed"}).json()
    assert [j["job_id"] for j in body["jobs"]] == ["a1-failed"]
    assert body["counts"]["all"] == 5


def test_foreign_or_unknown_location_filters_are_404(client, db, world):
    theirs_folder = folder(db, world["theirs"], "Bob's")
    assert client.get("/jobs", params={"project_id": world["theirs"].id}).status_code == 404
    assert client.get("/jobs", params={"project_id": "nope"}).status_code == 404
    response = client.get("/jobs", params={"folder_id": theirs_folder.id})
    assert response.status_code == 404
    assert response.json()["detail"] == "Pasta não encontrada"


def test_inconsistent_location_filters_are_422(client, world):
    assert client.get("/jobs", params={"folder_id": "root"}).status_code == 422
    assert client.get("/jobs", params={"project_id": world["b"].id,
                                       "folder_id": world["a1"].id}).status_code == 422


def test_list_items_carry_project_and_folder(client, world):
    jobs = {j["job_id"]: j for j in client.get("/jobs").json()["jobs"]}
    assert jobs["a1-ok"]["project"] == {"id": world["a"].id, "name": "Cliente A"}
    assert jobs["a1-ok"]["folder"] == {"id": world["a1"].id, "name": "Áudios"}
    assert jobs["a-root"]["folder"] is None
    assert "bob-job" not in jobs


def test_job_detail_carries_project_and_folder(client, db, world, fake_redis):
    job_id = "22222222-2222-4222-8222-222222222222"
    job(db, job_id, world["a"], world["a1"])
    fake_redis.set_job_status(job_id=job_id, job_type="main", status="completed", progress=100)
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200, response.text
    assert response.json()["project"] == {"id": world["a"].id, "name": "Cliente A"}
    assert response.json()["folder"] == {"id": world["a1"].id, "name": "Áudios"}


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

def test_api_key_list_shows_the_bound_project(client, world):
    keys = {k["name"]: k for k in client.get("/api-keys/").json()}
    assert keys["cliente-audio"]["project"] == {"id": world["a"].id, "name": "Cliente A"}
    assert keys["sem-projeto"]["project"] is None


def test_create_api_key_bound_by_name_creates_the_project(client, db):
    response = client.post("/api-keys/", json={"name": "robo", "project": "Transcrições automáticas"})
    assert response.status_code == 201
    created = db.query(Project).filter(Project.name == "Transcrições automáticas").one()
    assert response.json()["project"] == {"id": created.id, "name": "Transcrições automáticas"}
    assert db.query(APIKey).filter(APIKey.name == "robo").one().project_id == created.id


def test_create_api_key_by_id(client, db):
    p = project(db, "Existente")
    response = client.post("/api-keys/", json={"name": "robo", "project_id": p.id})
    assert response.json()["project"]["id"] == p.id


def test_create_api_key_with_foreign_project_is_404(client, db):
    theirs = project(db, "Do Bob", user_id=BOB)
    assert client.post("/api-keys/", json={"name": "robo", "project_id": theirs.id}).status_code == 404
    assert client.post("/api-keys/", json={"name": "r", "project": "X", "project_id": theirs.id}).status_code == 422
    assert db.query(APIKey).count() == 0


def test_patch_binds_and_unbinds(client, db, world):
    key = db.query(APIKey).filter(APIKey.name == "sem-projeto").one()
    response = client.patch(f"/api-keys/{key.id}", json={"project_id": world["b"].id})
    assert response.status_code == 200
    assert response.json()["project"] == {"id": world["b"].id, "name": "Beta"}
    db.refresh(key)
    assert key.project_id == world["b"].id

    response = client.patch(f"/api-keys/{key.id}", json={"project_id": None})
    assert response.status_code == 200 and response.json()["project"] is None
    db.refresh(key)
    assert key.project_id is None


def test_patch_with_foreign_project_is_404(client, db, world):
    key = db.query(APIKey).filter(APIKey.name == "sem-projeto").one()
    response = client.patch(f"/api-keys/{key.id}", json={"project_id": world["theirs"].id})
    assert response.status_code == 404
    db.refresh(key)
    assert key.project_id is None


def test_patch_someone_elses_key_is_404(client, db, world):
    theirs = APIKey(user_id=BOB, key_hash="hb", name="do-bob")
    db.add(theirs)
    db.commit()
    assert client.patch(f"/api-keys/{theirs.id}", json={"project_id": world["a"].id}).status_code == 404
