"""
Project limits and usage on the API (spec 0023): `folder_count` and `usage.projects` on
GET /projects, and GET /projects/{project_id} with `{project, limits, usage}`.

Authentication is the real one (JWT and X-API-Key through shared/auth.py). The usage is
counted by the same functions as the PROJECT_LIMIT / FOLDER_LIMIT refusals.
"""
from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import project_summaries, projects_api
from shared import projects as projects_module
from shared.database import get_db
from shared.models import Job, JobStatus, User
from tests.test_upload_projects import ALICE, BOB, add_folder, add_key, add_project, api_key, jwt
from tests.test_upload_projects import db  # noqa: F401  (fixture)

ALICE_KEY, BOB_KEY = "doc2md_sk_alice-usage", "doc2md_sk_bob-usage"


@pytest.fixture
def client(db, monkeypatch):  # noqa: F811
    settings = projects_module.get_settings()
    monkeypatch.setattr(settings, "max_projects_per_user", 10)
    monkeypatch.setattr(settings, "max_folders_per_project", 500)
    add_key(db, ALICE_KEY, user_id=ALICE)
    add_key(db, BOB_KEY, user_id=BOB)
    app = FastAPI()
    app.include_router(projects_api.router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


@pytest.fixture
def world(db):  # noqa: F811
    one = add_project(db, ALICE, "Um")
    two = add_project(db, ALICE, "Dois")
    two.archived_at = datetime(2026, 1, 1)  # archived still counts for PROJECT_LIMIT
    for name in ("a", "b", "c"):
        add_folder(db, one, name)
    theirs = add_project(db, BOB, "Deles")
    for name in ("x", "y"):
        add_folder(db, theirs, name)
    add_project(db, BOB, "Outro")
    add_project(db, BOB, "Mais um")
    db.add(Job(id="j1", user_id=ALICE, name="j1", filename="j1", status=JobStatus.COMPLETED, job_type="MAIN",
               project_id=one.id, created_at=datetime(2026, 1, 2)))
    db.commit()
    return one, two, theirs


@pytest.mark.parametrize("include", [None, "folders"])
def test_the_list_brings_folder_count_and_the_callers_project_usage(client, world, include):
    one, two, _ = world
    body = client.get("/projects", params={"include": include} if include else {}, headers=jwt()).json()
    counts = {p["id"]: p["folder_count"] for p in body["projects"]}
    assert counts == {one.id: 3, two.id: 0}  # every folder, with or without ?include=folders
    assert body["usage"] == {"projects": 2}  # archived included, no `folders` on the list
    assert body["limits"] == {"max_projects": 10, "max_folders_per_project": 500}


def test_the_detail_brings_the_summary_limits_and_usage(client, world):
    one, _, _ = world
    body = client.get(f"/projects/{one.id}", headers=jwt()).json()
    listed = next(p for p in client.get("/projects", headers=jwt()).json()["projects"] if p["id"] == one.id)
    assert body["project"] == listed  # the same ProjectSummary as the list
    assert body["project"]["job_count"] == 1 and "folders" not in body["project"]
    assert body["limits"] == {"max_projects": 10, "max_folders_per_project": 500}
    assert body["usage"] == {"projects": 2, "folders": 3}
    with_folders = client.get(f"/projects/{one.id}", params={"include": "folders"}, headers=jwt()).json()
    assert [f["name"] for f in with_folders["project"]["folders"]] == ["a", "b", "c"]


def test_the_detail_answers_an_api_key_like_a_jwt(client, world):
    one, _, _ = world
    by_key = client.get(f"/projects/{one.id}", headers=api_key(ALICE_KEY))
    assert by_key.status_code == 200
    assert by_key.json() == client.get(f"/projects/{one.id}", headers=jwt()).json()


@pytest.mark.parametrize("headers", [jwt(BOB), api_key(BOB_KEY)], ids=["jwt", "api_key"])
def test_another_users_project_or_a_missing_one_is_404(client, world, headers):
    one, _, theirs = world
    assert client.get(f"/projects/{one.id}", headers=headers).status_code == 404  # Alice's, read by Bob
    assert client.get("/projects/nope", headers=headers).status_code == 404
    assert client.get(f"/projects/{theirs.id}", headers=headers).status_code == 200


def test_usage_projects_is_the_callers_never_the_owners(db, world):  # noqa: F811
    _, _, theirs = world  # Bob's project (3 projects), as a project shared with Alice would be read
    alice = db.get(User, ALICE)
    body = project_summaries.get_project(include=None, project=theirs, user=alice, db=db)
    assert body.usage.projects == 2  # Alice's count: the owner's (3) would leak how many Bob has
    assert body.usage.folders == 2


def test_no_limit_still_reports_usage(client, world, monkeypatch):
    one, _, _ = world
    monkeypatch.setattr(projects_module.get_settings(), "max_projects_per_user", 0)
    monkeypatch.setattr(projects_module.get_settings(), "max_folders_per_project", 0)
    body = client.get(f"/projects/{one.id}", headers=jwt()).json()
    assert body["limits"] == {"max_projects": 0, "max_folders_per_project": 0}
    assert body["usage"] == {"projects": 2, "folders": 3}


@pytest.mark.parametrize("slack,refused", [(0, True), (1, False)])
def test_the_reported_usage_is_what_the_project_limit_refuses_at(client, db, world, monkeypatch,  # noqa: F811
                                                                  slack, refused):
    used = client.get("/projects", headers=jwt()).json()["usage"]["projects"]
    monkeypatch.setattr(projects_module.get_settings(), "max_projects_per_user", used + slack)
    if refused:
        with pytest.raises(HTTPException) as e:
            projects_module.get_or_create_project(db, ALICE, "Novo")
        assert e.value.detail["code"] == "PROJECT_LIMIT"
    else:
        assert projects_module.get_or_create_project(db, ALICE, "Novo")[1] is True


@pytest.mark.parametrize("slack,refused", [(0, True), (1, False)])
def test_the_reported_usage_is_what_the_folder_limit_refuses_at(client, db, world, monkeypatch,  # noqa: F811
                                                                 slack, refused):
    one, _, _ = world
    used = client.get(f"/projects/{one.id}", headers=jwt()).json()["usage"]["folders"]
    monkeypatch.setattr(projects_module.get_settings(), "max_folders_per_project", used + slack)
    if refused:
        with pytest.raises(HTTPException) as e:
            projects_module.get_or_create_folder(db, one, "nova")
        assert e.value.detail["code"] == "FOLDER_LIMIT"
    else:
        assert projects_module.get_or_create_folder(db, one, "nova")[1] is True


def _statements(db, client, params):
    seen = []

    def count(conn, cursor, statement, *args):
        seen.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        assert client.get("/projects", params=params, headers=jwt()).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return seen


@pytest.mark.parametrize("include", [None, "folders"])
def test_the_list_runs_a_fixed_number_of_queries(client, db, world, include):  # noqa: F811
    params = {"include": include} if include else {}
    few = len(_statements(db, client, params))
    for i in range(5):
        add_folder(db, add_project(db, ALICE, f"Extra {i}"), "f")
    many = _statements(db, client, params)
    assert len(many) == few  # not one query per project
    assert len([s for s in many if "FROM folders" in s and "GROUP BY folders.project_id" in s]) == 1


def test_resolve_is_not_captured_by_the_detail_route(client, world):
    response = client.get("/projects/resolve", params={"name": "Um"}, headers=jwt())
    assert response.status_code == 200 and response.json()["match"]["name"] == "Um"
