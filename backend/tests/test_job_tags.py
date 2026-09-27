"""Job tags: parsing, GET /jobs filters, GET /tags and PUT /jobs/{job_id}/tags."""
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import routes, tag_routes
from shared.auth import get_current_active_user
from shared.database import Base, get_db
from shared.models import Job, JobStatus, User
from shared.tags import InvalidTagsError, parse_tags, set_job_tags

ALICE = "user-alice"
BOB = "user-bob"


# --- parse_tags --------------------------------------------------------------

def test_tags_are_normalised_and_deduplicated():
    assert parse_tags(" Cliente X ,#reunião,  cliente   x, ,NF ") == ["cliente x", "reunião", "nf"]


def test_list_input_is_split_on_commas_too():
    assert parse_tags(["a,b", "B", "c"]) == ["a", "b", "c"]


def test_no_tags():
    assert parse_tags(None) == []
    assert parse_tags("  , ,") == []


def test_too_long_tag_is_rejected():
    with pytest.raises(InvalidTagsError):
        parse_tags("x" * 51)


def test_too_many_tags_are_rejected():
    with pytest.raises(InvalidTagsError):
        parse_tags(",".join(f"t{i}" for i in range(21)))


# --- API ---------------------------------------------------------------------

@pytest.fixture
def db():
    # One connection shared across threads: TestClient runs the app in another thread.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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


def add_job(db, job_id, user_id=ALICE, name="doc.pdf", source_type="file",
            status=JobStatus.COMPLETED, tags=(), day=1):
    job = Job(id=job_id, user_id=user_id, name=name, filename=name, source_type=source_type,
              status=status, job_type="MAIN", created_at=datetime(2026, 1, day))
    db.add(job)
    set_job_tags(job, list(tags))
    db.commit()
    return job


@pytest.fixture
def client(db, fake_redis, monkeypatch):
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("api.deps._redis_owner_matches", lambda job_id, user_id: False)
    app = FastAPI()
    app.include_router(tag_routes.router)
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: db.get(User, ALICE)
    return TestClient(app)


def ids(response):
    return [j["job_id"] for j in response.json()["jobs"]]


def test_list_filters_by_one_tag_and_by_all_given_tags(client, db):
    add_job(db, "j1", tags=["cliente-x", "nf"], day=1)
    add_job(db, "j2", tags=["cliente-x"], day=2)
    add_job(db, "j3", tags=["outro"], day=3)

    assert ids(client.get("/jobs", params={"tag": "cliente-x"})) == ["j2", "j1"]
    assert ids(client.get("/jobs", params=[("tag", "cliente-x"), ("tag", "NF")])) == ["j1"]


def test_list_items_carry_tags_and_kind(client, db):
    add_job(db, "a1", name="talk.mp3", source_type="audio", tags=["b", "a"])
    job = client.get("/jobs").json()["jobs"][0]
    assert job["tags"] == ["a", "b"]
    assert job["kind"] == "transcription"


def test_list_filters_by_kind_and_name(client, db):
    add_job(db, "d1", name="Relatório anual.pdf", day=1)
    add_job(db, "a1", name="entrevista.mp3", source_type="audio", day=2)
    add_job(db, "i1", name="foto.png", source_type="image", day=3)

    assert ids(client.get("/jobs", params={"kind": "document"})) == ["d1"]
    assert ids(client.get("/jobs", params={"kind": "transcription"})) == ["a1"]
    assert ids(client.get("/jobs", params={"q": "anual"})) == ["d1"]


def test_counts_ignore_the_status_filter_but_total_does_not(client, db):
    add_job(db, "c1", status=JobStatus.COMPLETED, day=1)
    add_job(db, "f1", status=JobStatus.FAILED, day=2)
    add_job(db, "p1", status=JobStatus.PENDING, day=3)

    body = client.get("/jobs", params={"status": "failed"}).json()
    assert body["total"] == 1
    assert ids_of(body) == ["f1"]
    assert body["counts"] == {"all": 3, "queued": 1, "processing": 0, "completed": 1,
                              "failed": 1, "cancelled": 0}


def ids_of(body):
    return [j["job_id"] for j in body["jobs"]]


def test_list_only_shows_the_callers_jobs(client, db):
    add_job(db, "mine", tags=["x"])
    add_job(db, "theirs", user_id=BOB, tags=["x"])
    assert ids(client.get("/jobs", params={"tag": "x"})) == ["mine"]


def test_invalid_filters_are_422(client):
    assert client.get("/jobs", params={"status": "done"}).status_code == 422
    assert client.get("/jobs", params={"kind": "video"}).status_code == 422


def test_tag_counts_are_per_user(client, db):
    add_job(db, "j1", tags=["a", "b"])
    add_job(db, "j2", tags=["a"])
    add_job(db, "theirs", user_id=BOB, tags=["a", "secret"])

    assert client.get("/tags").json() == {"tags": [{"tag": "a", "count": 2}, {"tag": "b", "count": 1}]}


def test_put_replaces_and_normalises_tags(client, db):
    add_job(db, "j1", tags=["old"])
    response = client.put("/jobs/j1/tags", json={"tags": ["Novo", "#nf", "novo"]})
    assert response.status_code == 200
    assert response.json() == {"job_id": "j1", "tags": ["nf", "novo"]}
    assert client.put("/jobs/j1/tags", json={"tags": []}).json()["tags"] == []


def test_put_on_someone_elses_job_is_404(client, db):
    add_job(db, "theirs", user_id=BOB, tags=["x"])
    assert client.put("/jobs/theirs/tags", json={"tags": ["mine"]}).status_code == 404
    assert db.get(Job, "theirs").tags == ["x"]
