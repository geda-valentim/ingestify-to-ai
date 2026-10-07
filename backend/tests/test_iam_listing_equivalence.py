"""
Listing equivalence (spec 0014 CA4, §4.5).

Every listing converted to `visible(...)` must return exactly the IDs the legacy
inline filter (`Model.user_id == current_user.id`) returned. For each listing the
"before" is that legacy query, written out here as it stood in the route before
the conversion; the "after" is the converted endpoint. Both are compared for a
user with data, another user with data and a user with none, under every
IAM_MODE (the predicate has no shadow: it *is* the legacy filter in all modes).

The listings: GET /jobs, /search, /projects (and its job/folder/key counts),
/projects/resolve, /tags, /api-keys and /datalakes (merged with #48; the face
and Full Analysis routes of #48 add no listing: their jobs are listed by
GET /jobs, which the fixture covers with image jobs too).
"""

import uuid
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import apikey_routes, datalake_routes, projects_api, routes, tag_routes
from api.iam_deps import visible
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import Base, get_db
from shared.models import APIKey, DatalakeConnection, Folder, Job, JobStatus, JobTag, LiveSession, Project, User
from shared.projects import name_key
from shared.tags import set_job_tags

ALICE, BOB, CAROL = "user-alice", "user-bob", "user-carol"  # carol has no data
USERS = (ALICE, BOB, CAROL)
MODES = ("off", "shadow", "enforce")


def key_id(owner, n):
    """API key ids are UUIDs (the response model parses them)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{owner}-k{n}"))


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        User(id=uid, email=f"{uid}@example.com", username=uid, hashed_password="x", is_active=True)
        for uid in USERS
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def world(db):
    """Two users with interleaved data of every listed kind; carol has nothing."""
    for owner, tag in ((ALICE, "a"), (BOB, "b")):
        proj = Project(id=f"{owner}-p1", user_id=owner, name="Shared Name", name_key=name_key("Shared Name"))
        other = Project(id=f"{owner}-p2", user_id=owner, name=f"Only {tag}", name_key=name_key(f"Only {tag}"))
        db.add_all([proj, other])
        db.flush()
        fold = Folder(id=f"{owner}-f1", user_id=owner, project_id=proj.id, name="F", name_key="f")
        db.add(fold)
        db.flush()
        for n, (status, folder_id, kind) in enumerate([
            (JobStatus.COMPLETED, None, "MAIN"),
            (JobStatus.FAILED, fold.id, "MAIN"),
            (JobStatus.PENDING, fold.id, "MAIN"),
            (JobStatus.COMPLETED, None, "PAGE"),
        ]):
            j = Job(id=f"{owner}-j{n}", user_id=owner, name=f"doc {n}", filename=f"doc{n}.pdf",
                    status=status, job_type=kind, created_at=datetime(2026, 1, 1 + n),
                    project_id=proj.id, folder_id=folder_id)
            db.add(j)
            set_job_tags(j, ["common", f"only-{tag}"] if n % 2 == 0 else ["common"])
        # A completed live job, so /search's SQL publication check is exercised.
        db.add(Job(id=f"{owner}-live", user_id=owner, name="live", filename="live.pcm", status=JobStatus.COMPLETED,
                   job_type="MAIN", source_type="audio", project_id=proj.id, created_at=datetime(2026, 2, 1)))
        db.flush()
        db.add(LiveSession(job_id=f"{owner}-live", state="completed", backend="x", model="m", language="pt",
                           worker_id="w", generation=7))
        db.add_all([
            APIKey(id=key_id(owner, 1), user_id=owner, key_hash=f"h-{owner}-1", name="bound", project_id=proj.id),
            APIKey(id=key_id(owner, 2), user_id=owner, key_hash=f"h-{owner}-2", name="free"),
        ])
        # Datalake connections with the same names for both users (GET /datalakes
        # orders by name), one disabled: the listing shows disabled ones too.
        db.add_all([
            DatalakeConnection(id=f"{owner}-dl{n}", user_id=owner, name=name, provider="s3",
                               config={}, enabled=n != 2, credentials_encrypted=b"sealed")
            for n, name in ((1, "Lake"), (2, "Archive"))
        ])
        # An image job (Full Analysis / faces), listed by GET /jobs like any MAIN job.
        db.add(Job(id=f"{owner}-image", user_id=owner, name="img", filename="img.png", status=JobStatus.COMPLETED,
                   job_type="MAIN", source_type="image", project_id=proj.id, created_at=datetime(2026, 3, 1)))
    # An orphan (user_id NULL after a user deletion) is nobody's, before and after.
    db.add(Job(id="orphan", user_id=None, name="o", filename="o.pdf", status=JobStatus.COMPLETED, job_type="MAIN"))
    db.commit()


class FakeES:
    """Filters by user_id like the real index, and returns every live hit too."""

    def __init__(self, db):
        self.db = db

    def search_jobs(self, query, user_id, limit):
        hits = []
        for job in self.db.query(Job).order_by(Job.id):
            live = job.source_type == "audio"
            # Live hits are returned for *every* user, as a misindexed document would
            # be: only the SQL publication check (the scope predicate) filters them.
            if job.user_id == user_id or live:
                meta = {"input_mode": "live", "generation": 7} if live else {}
                hits.append({"job_id": job.id, "filename": job.filename, "metadata": meta,
                             "markdown_content": "x"})
        return hits[:limit]


@pytest.fixture
def client(db, world, fake_redis, monkeypatch):
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(routes, "get_es_client", lambda: FakeES(db))
    monkeypatch.setattr("api.deps._redis_owner_matches", lambda job_id, user_id: False)
    monkeypatch.setattr("api.deps._redis_job_status", lambda job_id: None)
    app = FastAPI()
    app.include_router(apikey_routes.router, prefix="/api-keys")
    app.include_router(projects_api.router)
    app.include_router(tag_routes.router)
    app.include_router(routes.router)
    app.include_router(datalake_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: db.get(User, app.state.user)
    tc = TestClient(app)

    def as_user(uid):
        app.state.user = uid
        return tc

    return as_user


@pytest.fixture(params=MODES)
def mode(request, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "iam_mode", request.param)
    monkeypatch.setattr(s, "admin_user_ids", "")
    return request.param


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


# -- the legacy queries, as they stood in the routes before §8.4 ---------------------


def legacy_jobs(db, uid):
    return {j.id for j in db.query(Job).filter(Job.user_id == uid, func.upper(Job.job_type) == "MAIN")}


def legacy_published_live(db, uid, live_ids):
    return set(dict(
        db.query(Job.id, LiveSession.generation)
        .join(LiveSession, LiveSession.job_id == Job.id)
        .filter(Job.id.in_(live_ids), Job.user_id == uid,
                Job.status == JobStatus.COMPLETED, LiveSession.state == "completed").all()
    ))


def legacy_projects(db, uid):
    return {p.id for p in db.query(Project).filter(Project.user_id == uid)}


def legacy_project_counts(db, uid):
    rows = (
        db.query(Job.project_id, func.count(Job.id))
        .filter(Job.user_id == uid, Job.job_type == "MAIN", Job.project_id.isnot(None))
        .group_by(Job.project_id).all()
    )
    return dict(rows)


def legacy_project_stats(db, uid):
    """root/failed/active counts and last_job_at per project, from the legacy owner filter."""
    stats = {}
    q = db.query(Job).filter(Job.user_id == uid, Job.job_type == "MAIN", Job.project_id.isnot(None))
    for j in q:
        st = stats.setdefault(j.project_id, {"root_job_count": 0, "failed_count": 0, "active_count": 0,
                                             "last_job_at": None})
        st["root_job_count"] += j.folder_id is None
        st["failed_count"] += j.status == JobStatus.FAILED
        st["active_count"] += j.status in (JobStatus.PENDING, JobStatus.PROCESSING)
        if st["last_job_at"] is None or j.created_at > st["last_job_at"]:
            st["last_job_at"] = j.created_at
    return {pid: {**st, "last_job_at": st["last_job_at"].isoformat()} for pid, st in stats.items()}


def legacy_folder_counts(db, uid):
    rows = (
        db.query(Job.folder_id, func.count(Job.id))
        .filter(Job.user_id == uid, Job.job_type == "MAIN", Job.project_id.isnot(None), Job.folder_id.isnot(None))
        .group_by(Job.folder_id).all()
    )
    return dict(rows)


def legacy_project_keys(db, uid):
    return {k for (k,) in db.query(APIKey.id).filter(APIKey.user_id == uid, APIKey.project_id.isnot(None))}


def legacy_folders(db, uid):
    return {f.id for f in db.query(Folder).filter(Folder.user_id == uid)}


def legacy_tags(db, uid):
    return dict(
        db.query(JobTag.tag, func.count(JobTag.job_id))
        .join(Job, Job.id == JobTag.job_id)
        .filter(Job.user_id == uid)
        .group_by(JobTag.tag).all()
    )


def legacy_keys(db, uid):
    return {k.id for k in db.query(APIKey).filter(APIKey.user_id == uid)}


def legacy_datalakes(db, uid):
    """GET /datalakes at origin/main: ids in the order the route returned them."""
    return [c.id for c in db.query(DatalakeConnection)
            .filter(DatalakeConnection.user_id == uid).order_by(DatalakeConnection.name).all()]


# -- CA4 ------------------------------------------------------------------------------


@pytest.mark.parametrize("uid", USERS)
def test_jobs_listing_returns_the_legacy_ids(client, db, mode, uid):
    body = _ok(client(uid).get("/jobs", params={"limit": 100}))
    assert {j["job_id"] for j in body["jobs"]} == legacy_jobs(db, uid)
    assert body["total"] == len(legacy_jobs(db, uid))
    # The `all` view (children included) is the same owner filter.
    body = _ok(client(uid).get("/jobs", params={"limit": 100, "job_type": "all"}))
    assert {j["job_id"] for j in body["jobs"]} == {j.id for j in db.query(Job).filter(Job.user_id == uid)}
    assert "orphan" not in {j["job_id"] for j in body["jobs"]}


@pytest.mark.parametrize("uid", USERS)
def test_search_returns_the_legacy_ids(client, db, mode, uid):
    body = _ok(client(uid).get("/search", params={"query": "x", "limit": 100}))
    got = {r["job_id"] for r in body["results"]}
    hits = FakeES(db).search_jobs("x", uid, 100)
    live_ids = {h["job_id"] for h in hits if h["metadata"].get("input_mode") == "live"}
    published = legacy_published_live(db, uid, live_ids)
    expected = {h["job_id"] for h in hits if h["job_id"] not in live_ids or h["job_id"] in published}
    assert got == expected
    # Someone else's live hit never survives the SQL check.
    assert all(j.startswith(uid) for j in got)


@pytest.mark.parametrize("uid", USERS)
def test_projects_listing_and_counts_return_the_legacy_ids(client, db, mode, uid):
    body = _ok(client(uid).get("/projects", params={"include": "folders"}))
    projects = body["projects"]
    assert {p["id"] for p in projects} == legacy_projects(db, uid)
    assert {p["id"]: p["job_count"] for p in projects if p["job_count"]} == legacy_project_counts(db, uid)
    assert {k["id"] for p in projects for k in p["api_keys"]} == legacy_project_keys(db, uid)
    assert {f["id"] for p in projects for f in p["folders"]} == legacy_folders(db, uid)
    # The other counts read through `scope.of(Job)` too.
    fields = ("root_job_count", "failed_count", "active_count", "last_job_at")
    got = {p["id"]: {f: p[f] for f in fields} for p in projects if p["job_count"]}
    assert got == legacy_project_stats(db, uid)
    assert {f["id"]: f["job_count"] for p in projects for f in p["folders"] if f["job_count"]} \
        == legacy_folder_counts(db, uid)


@pytest.mark.parametrize("uid", USERS)
def test_project_resolve_matches_only_the_callers_project(client, db, mode, uid):
    body = _ok(client(uid).get("/projects/resolve", params={"name": "shared name"}))
    legacy = db.query(Project).filter(Project.user_id == uid, Project.name_key == name_key("Shared Name")).first()
    assert (body["match"] or {}).get("id") == (legacy.id if legacy else None)


@pytest.mark.parametrize("uid", USERS)
def test_tags_listing_returns_the_legacy_counts(client, db, mode, uid):
    body = _ok(client(uid).get("/tags"))
    assert {t["tag"]: t["count"] for t in body["tags"]} == legacy_tags(db, uid)


@pytest.mark.parametrize("uid", USERS)
def test_api_keys_listing_returns_the_legacy_ids(client, db, mode, uid):
    body = _ok(client(uid).get("/api-keys/"))
    assert {k["id"] for k in body} == legacy_keys(db, uid)
    # The bound project is named only when it is the caller's (same owner as the key).
    bound = {k["id"]: (k["project"] or {}).get("id") for k in body}
    assert bound == {k: (f"{uid}-p1" if k == key_id(uid, 1) else None) for k in legacy_keys(db, uid)}


@pytest.mark.parametrize("uid", USERS)
def test_datalakes_listing_returns_the_legacy_ids(client, db, mode, uid):
    body = _ok(client(uid).get("/datalakes"))
    assert [c["id"] for c in body["connections"]] == legacy_datalakes(db, uid)
    # Credentials never leave the listing, before and after.
    assert all("credentials_encrypted" not in c for c in body["connections"])


def test_users_with_data_see_disjoint_sets_and_carol_sees_nothing(client, db, mode):
    """Sanity of the fixture itself: the comparisons above are not vacuous."""
    for uid in (ALICE, BOB):
        assert legacy_jobs(db, uid) and legacy_projects(db, uid) and legacy_tags(db, uid) and legacy_keys(db, uid)
    assert not (legacy_jobs(db, ALICE) & legacy_jobs(db, BOB))
    assert _ok(client(CAROL).get("/jobs"))["jobs"] == []
    assert _ok(client(CAROL).get("/projects"))["projects"] == []
    assert _ok(client(CAROL).get("/tags"))["tags"] == []
    assert _ok(client(CAROL).get("/api-keys/")) == []
    assert legacy_datalakes(db, ALICE) and not set(legacy_datalakes(db, ALICE)) & set(legacy_datalakes(db, BOB))
    assert _ok(client(CAROL).get("/datalakes"))["connections"] == []


# -- the SQL itself is unchanged -------------------------------------------------------


def _sql(clause):
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("model,perm,related", [
    (Job, "jobs.read", ()),
    (Job, "search.query", ()),
    (Project, "projects.read", (Job, APIKey, Folder)),
    (APIKey, "api_keys.read", (Project,)),
    (DatalakeConnection, "datalakes.read", ()),
])
def test_scope_predicates_compile_to_the_legacy_filters(mode, model, perm, related):
    import asyncio

    me = User(id=ALICE)
    scope = asyncio.run(visible(model, perm)(user=me))
    assert _sql(scope.predicate) == _sql(model.user_id == ALICE)
    for other in related:
        assert _sql(scope.of(other)) == _sql(other.user_id == ALICE)


def test_tags_query_text_is_unchanged(client, db, mode):
    """The statement /tags sends is byte-for-byte the legacy one (same plan, same index)."""
    statements = []

    def capture(conn, cursor, statement, params, context, executemany):
        if "job_tags" in statement:
            statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        _ok(client(ALICE).get("/tags"))
        legacy_tags(db, ALICE)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    route_sql, legacy_sql = statements
    # The legacy helper above omits the ORDER BY; everything before it is identical.
    assert route_sql.split(" ORDER BY")[0] == legacy_sql
    assert "jobs.user_id = ?" in route_sql
