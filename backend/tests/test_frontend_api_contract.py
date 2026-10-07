"""
The contract between `frontend/lib/api.ts` and this API.

Why this file exists
--------------------
Six P0s shipped at once because nothing on either side of the wire could
disagree out loud. `npx tsc --noEmit` exits 0 while the frontend declares
`list(): Promise<JobStatusResponse[]>` and receives `{total, limit, offset,
jobs}`, because `response.json()` is `any`: the declared return type is not a
check, it is an unverified claim. On this side, `list_jobs` declares no
`response_model`, so the OpenAPI schema is equally silent. Two layers of types,
zero enforcement, and "Meus Jobs" rendered empty for every user.

What is pinned here
-------------------
Only the specific things the frontend depends on, in four layers:

  1. `TestRoutesTheFrontendCalls` - a hand-kept table of every (method, path)
     `frontend/lib/api.ts` issues; each must exist in the generated OpenAPI
     schema, and the near-misses that silently resolve to a *different* route
     must not.
  2. `TestFrontendCallSitesResolve` - the same check without the hand-keeping:
     the URLs are parsed straight out of `frontend/lib/api.ts` and matched
     against the live schema. This is the layer that would have caught P0-3a and
     P0-4 unaided; layer 1 only helps someone who remembers to edit the table.
  3. `TestDeclaredResponseShapes` / `TestLiveResponseShapes` - the response keys
     the frontend actually reads. Declared where a `response_model` exists,
     and from real in-process responses where it does not: `GET /jobs`,
     `GET /search` and the page-retry route declare no `response_model`, so the
     schema is silent about exactly the bugs that hurt most.
  4. `TestPublishedOpenApiDocumentIsFresh` - `frontend/docs/doc2md_openapi.json`
     is generated output and must match its generator.

What is deliberately NOT pinned
-------------------------------
  - The schema as *the contract*. Asserting all 27 operations field-by-field
    would fail on every unrelated docstring edit, and a test that cries wolf
    gets deleted. (Layer 4 compares the whole document, but only against the
    app that generated it, where the fix is one mechanical command.)
  - Endpoints the frontend does not call (`/admin/*`, `/transcribe`,
    `/convert`). They have their own callers and their own contracts.
  - Business behaviour: ownership, retry limits, conversion. Covered elsewhere.
  - Exhaustive field lists. Assertions name the fields the frontend reads;
    adding a field to a response must not fail this file.
  - How the frontend *parses* a correct response. Nothing on this side can see
    that `apiKeysApi.list()` did `data.api_keys || []` against a bare array, or
    that `revoke()` called `.json()` on a 204. What layers 3 and 4 do give is
    the other half: once the client is right, the server cannot drift away from
    it silently.

When you change a route the frontend calls, this file should fail. That is the
whole point. Update the table below in the same commit as the frontend.

No Docker, no live services: SQLite with the real models, fakeredis through the
real RedisClient, and a minimal in-process ASGI call (see
`test_page_pdf_endpoint.py` for the same pattern).
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database import Base, get_db
from shared.models import Job, Page, User, JobStatus as DBJobStatus
from shared.auth import get_current_active_user

import api.routes as routes


# ---------------------------------------------------------------------------
# The table: every call site in frontend/lib/api.ts.
#
# `note` records why the frontend needs it, so a future reader can tell whether
# a route may be moved. Keep this list in sync with lib/api.ts, not with the
# router - divergence between the two is the failure this file catches.
# ---------------------------------------------------------------------------
FRONTEND_OPERATIONS = [
    ("post", "/transcribe/live/sessions", "liveApi.create - microphone admission"),
    ("get", "/transcribe/live/sessions/{job_id}", "liveApi.getStatus - durable live state"),
    ("delete", "/transcribe/live/sessions/{job_id}", "liveApi.cancel - cancel capture"),
    ("post", "/auth/register", "authApi.register"),
    ("post", "/auth/login", "authApi.login"),
    ("get", "/auth/me", "authApi.me"),
    ("post", "/convert", "jobsApi.convert"),
    ("post", "/upload", "jobsApi.upload - dashboard upload"),
    ("get", "/images/capabilities", "jobsApi.imageCapabilities - upload limits and caption tasks"),
    ("post", "/images/describe/upload", "jobsApi.upload - image description"),
    ("post", "/images/ocr/upload", "jobsApi.upload - image OCR"),
    ("post", "/images/analyze/upload", "jobsApi.upload - vision tasks and generation controls"),
    ("get", "/jobs", "jobsApi.list - the 'My Jobs' page"),
    ("get", "/jobs/{job_id}", "jobsApi.getStatus - job detail polling"),
    ("delete", "/jobs/{job_id}", "jobsApi.delete - delete from list and detail"),
    ("get", "/jobs/{job_id}/result", "jobsApi.getResult"),
    ("get", "/jobs/{job_id}/pages", "jobsApi.getPages"),
    ("get", "/jobs/{job_id}/pages/{page_number}/pdf", "jobsApi.getPagePdf"),
    ("post", "/jobs/{job_id}/pages/{page_number}/retry",
     "jobsApi.retryPage - single and bulk page retry"),
    ("get", "/search", "jobsApi.search - the search box on 'My Jobs'"),
    ("get", "/api-keys/", "apiKeysApi.list"),
    ("post", "/api-keys/", "apiKeysApi.create"),
    ("delete", "/api-keys/{key_id}", "apiKeysApi.revoke"),
    ("patch", "/api-keys/{key_id}", "apiKeysApi.setProject - the key's bound project"),
    ("get", "/projects", "projectsApi.list - upload combobox and /jobs sidebar"),
    ("get", "/projects/resolve", "projectsApi.resolve - 'use X' vs 'create X' while typing"),
    ("get", "/projects/{project_id}/folders/resolve", "projectsApi.resolveFolder"),
]

# Paths the frontend must never call, because each one resolves to something
# else and answers confidently with the wrong thing.
SHADOWED_PATHS = [
    (
        "/jobs/search",
        "Matches GET /jobs/{job_id} with job_id='search': the search box got a "
        "404 'Job não encontrado' on every keystroke instead of a route error. "
        "The real route is GET /search.",
    ),
    (
        "/jobs/{job_id}/retry",
        "Never existed. Page retry is addressed by (job id, page number) - a "
        "retry mints a new page job, so the server must know which page of "
        "which document. The real route is POST "
        "/jobs/{job_id}/pages/{page_number}/retry.",
    ),
]


@pytest.fixture(scope="module")
def schema():
    """The OpenAPI document the live app actually serves."""
    from api.main import app

    return app.openapi()


def _operations(schema):
    return {
        (method, path)
        for path, item in schema["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }


class TestRoutesTheFrontendCalls:
    @pytest.mark.parametrize(
        "method,path,note",
        FRONTEND_OPERATIONS,
        ids=[f"{m.upper()} {p}" for m, p, _ in FRONTEND_OPERATIONS],
    )
    def test_operation_exists(self, schema, method, path, note):
        assert (method, path) in _operations(schema), (
            f"{method.upper()} {path} is gone, but the frontend still calls it "
            f"({note}). Either restore the route or fix frontend/lib/api.ts."
        )

    @pytest.mark.parametrize(
        "path,why",
        SHADOWED_PATHS,
        ids=[p for p, _ in SHADOWED_PATHS],
    )
    def test_shadowed_path_is_not_a_route(self, schema, path, why):
        assert path not in schema["paths"], (
            f"{path} became a real route. It used to be a trap: {why} If it is "
            f"now intentional, update frontend/lib/api.ts and this test together."
        )

    def test_jobs_detail_route_is_what_swallowed_jobs_search(self, schema):
        """The premise of the /jobs/search trap: a greedy single-segment param."""
        assert "/jobs/{job_id}" in schema["paths"]
        assert "get" in schema["paths"]["/jobs/{job_id}"]


API_CLIENT = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api.ts"

_API_URL_MARKER = "${API_URL}"


def _template_body(source, start):
    """
    The rest of the template literal beginning at `source[start]`, up to its
    closing backtick.

    Hand-written rather than a regex because interpolations nest: `list()` builds
    ``\N{GRAVE ACCENT}${API_URL}/jobs${p.toString() ? \N{GRAVE ACCENT}?${p}\N{GRAVE ACCENT} : ""}\N{GRAVE ACCENT}``, and a
    non-greedy `[^`]*` stops at the *inner* backtick and reports a garbage path.
    """
    depth = 0
    i = start
    while i < len(source):
        char = source[i]
        if char == "$" and source[i:i + 2] == "${":
            depth += 1
            i += 2
            continue
        if char == "}" and depth:
            depth -= 1
        elif char == "`" and depth == 0:
            return source[start:i]
        i += 1
    raise AssertionError("unterminated template literal after ${API_URL}")


def _strip_interpolations(text):
    """Replace every balanced `${...}` with a single `{}` placeholder."""
    out, depth, i = [], 0, 0
    while i < len(text):
        if text[i:i + 2] == "${":
            if depth == 0:
                out.append("{}")
            depth += 1
            i += 2
            continue
        if text[i] == "}" and depth:
            depth -= 1
            i += 1
            continue
        if depth == 0:
            out.append(text[i])
        i += 1
    return "".join(out)


def _client_paths():
    """The URL paths frontend/lib/api.ts actually builds, with `${x}` -> `{}`."""
    source = API_CLIENT.read_text(encoding="utf-8")
    paths = set()
    start = source.find(_API_URL_MARKER)
    while start != -1:
        body = _template_body(source, start + len(_API_URL_MARKER))
        path = _strip_interpolations(body).split("?")[0]
        # A trailing `{}` is an interpolated query string, not a path segment.
        while path.endswith("{}"):
            path = path[: -len("{}")]
        paths.add(path or "/")
        start = source.find(_API_URL_MARKER, start + 1)
    return sorted(paths)


def _resolves(client_path, schema_paths):
    """
    Does `client_path` reach a declared route?

    A literal client segment matches only an identical literal schema segment; a
    `{}` (an interpolated value) may also match a `{param}`. That asymmetry is
    the whole point: `/jobs/search` has two literal segments and therefore does
    *not* legitimately reach `/jobs/{job_id}` - even though FastAPI's router
    will happily route it there and answer 404 "Job não encontrado".
    """
    client = client_path.strip("/").split("/")
    for candidate in schema_paths:
        schema = candidate.strip("/").split("/")
        if len(schema) != len(client):
            continue
        if all(
            c == s or (c == "{}" and s.startswith("{") and s.endswith("}"))
            for c, s in zip(client, schema)
        ):
            return candidate
    return None


class TestFrontendCallSitesResolve:
    """
    The self-maintaining half: parse the URLs out of `frontend/lib/api.ts` and
    check each one against the live schema. This is what was missing - P0-3a and
    P0-4 were both a client calling a path that does not exist, and the table
    above only helps if a human remembers to update it.

    Paths only. Methods and response bodies are pinned by the other classes;
    inferring the verb from surrounding source would be brittle enough to rot.
    """

    def test_the_client_is_where_we_think_it_is(self):
        # The api image does not ship the frontend, so absence of the whole
        # frontend tree means "not in this checkout", not "moved". Only a
        # present frontend that has lost api.ts is a real failure.
        if not API_CLIENT.parent.parent.exists():
            pytest.skip("frontend not present in this checkout (e.g. inside the api image)")

        assert API_CLIENT.exists(), (
            f"{API_CLIENT} moved. Point this test at the new location - do not "
            f"delete it, it is the only automated link between the two sides."
        )

    def test_every_url_the_client_builds_reaches_a_route(self, schema):
        if not API_CLIENT.exists():
            pytest.skip("frontend not present in this checkout")

        schema_paths = list(schema["paths"])
        unresolved = {
            path: _resolves(path, schema_paths)
            for path in _client_paths()
        }
        broken = sorted(p for p, hit in unresolved.items() if hit is None)

        assert not broken, (
            "frontend/lib/api.ts builds URLs that are not routes: "
            + ", ".join(broken)
            + ". Note that some of these still get a response - `/jobs/search` "
            "routes to GET /jobs/{job_id} and answers a confident 404 - which "
            "is why this has to be checked rather than noticed in the browser."
        )


OPENAPI_DOC = (
    Path(__file__).resolve().parents[2] / "frontend" / "docs" / "doc2md_openapi.json"
)

REGENERATE = (
    "cd backend && python -c \"import json; from api.main import app; "
    "json.dump(app.openapi(), open('../frontend/docs/doc2md_openapi.json','w'), "
    "indent=2, ensure_ascii=False)\""
)


class TestPublishedOpenApiDocumentIsFresh:
    """
    `frontend/docs/doc2md_openapi.json` is a *generated* artifact, and it had
    silently fallen ten operations behind the app - including `DELETE
    /jobs/{job_id}` and the page-retry route, i.e. two of the routes these P0s
    were about. `info.version` is pinned at "1.0.0" on both sides, so it signals
    nothing; without something mechanical, drift is invisible.

    This is the one place a whole-schema comparison earns its keep: the file is
    not a hand-written contract to be reconciled, it is output, and the fix for a
    failure here is to re-run one command. (Pinning the schema as *the contract*
    is a different thing, and this file deliberately does not do it - see the
    module docstring.)
    """

    def test_committed_document_matches_the_live_app(self, schema):
        if not OPENAPI_DOC.exists():
            pytest.skip("frontend docs not present in this checkout")

        published = json.loads(OPENAPI_DOC.read_text(encoding="utf-8"))

        live_ops = _operations(schema)
        published_ops = _operations(published)
        assert published_ops == live_ops, (
            "frontend/docs/doc2md_openapi.json is stale.\n"
            f"  missing from the doc: {sorted(live_ops - published_ops)}\n"
            f"  no longer in the app: {sorted(published_ops - live_ops)}\n"
            f"Regenerate it:\n  {REGENERATE}"
        )
        assert published["components"]["schemas"] == schema["components"]["schemas"], (
            "The published schema components drifted from the app. "
            f"Regenerate:\n  {REGENERATE}"
        )


class TestDeclaredResponseShapes:
    """Shape facts the schema *can* prove, because these routes declare models."""

    def test_api_keys_list_is_a_bare_array(self, schema):
        """apiKeysApi.list used to do `data.api_keys || []` - always [] here."""
        content = schema["paths"]["/api-keys/"]["get"]["responses"]["200"]["content"]
        body = content["application/json"]["schema"]
        assert body.get("type") == "array", (
            "GET /api-keys/ answers a bare array (response_model=List[APIKeyInfo]). "
            "If it grows an envelope, apiKeysApi.list() must unwrap it."
        )

    def test_api_key_revoke_answers_204_with_no_body(self, schema):
        """apiKeysApi.revoke must not call response.json() on an empty body."""
        responses = schema["paths"]["/api-keys/{key_id}"]["delete"]["responses"]
        assert "204" in responses, "revoke is documented as No Content"
        assert not responses["204"].get("content"), (
            "204 carries no body. The client deliberately does not parse one; "
            "if a body is added, apiKeysApi.revoke() must start reading it."
        )

    def test_page_job_id_is_nullable_and_not_a_uuid(self, schema):
        """
        `PageJobInfo.job_id` used to be a required UUID while the routes emitted
        'pending-3' / 'page-3' for pages the split task had not created yet.
        Pydantic rejected those, FastAPI turned the rejection into a 500, and
        GET /jobs/{job_id} was unusable for the whole split window.
        """
        page_info = schema["components"]["schemas"]["PageJobInfo"]
        job_id = page_info["properties"]["job_id"]
        variants = job_id.get("anyOf", [job_id])

        assert any(v.get("type") == "null" for v in variants), (
            "job_id must admit null: a listed page can legitimately have no job "
            "yet. Making it required again brings back the 500."
        )
        assert not any(v.get("format") == "uuid" for v in variants), (
            "job_id must not be uuid-formatted. Job ids are opaque strings "
            "everywhere else (path params are `str`, Job.id is String(36)); "
            "parsing them only at the serialization boundary converts data "
            "surprises into 500s."
        )
        assert "job_id" not in page_info.get("required", [])

    def test_job_status_pages_use_page_job_info(self, schema):
        """The nullability above only helps if GET /jobs/{id} shares the model."""
        pages = schema["components"]["schemas"]["JobStatusResponse"]["properties"]["pages"]
        assert "PageJobInfo" in json.dumps(pages)


# ---------------------------------------------------------------------------
# Layer 2: live responses, for the routes OpenAPI cannot describe.
# ---------------------------------------------------------------------------

ALICE_ID = "user-alice"
MAIN_JOB_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def alice(db):
    user = User(id=ALICE_ID, email="alice@example.com", username="alice",
                hashed_password="x")
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def app(db, alice, fake_redis, monkeypatch):
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("api.deps._redis_job_status", lambda job_id: None)
    monkeypatch.setattr("api.deps._redis_owner_matches", lambda job_id, user_id: False)

    application = FastAPI()
    application.include_router(routes.router)
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[get_current_active_user] = lambda: alice
    return application


class _Response:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body

    def json(self):
        return json.loads(self.body)


def _request(app, method, path, query=""):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(b"host", b"localhost:8000")],
        "client": ("127.0.0.1", 51234),
        "server": ("localhost", 8000),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages
                    if m["type"] == "http.response.body")
    return _Response(start["status"], body)


class TestLiveResponseShapes:
    """
    These four routes are where the schema has nothing to say, so the frontend
    was free to be wrong about them - and was, three times out of four.
    """

    def test_jobs_list_answers_an_envelope_not_an_array(self, app, db, fake_redis):
        """
        P0-1. `jobsApi.list()` claimed `JobStatusResponse[]`; `jobsData || []`
        yielded a truthy object, `displayJobs.length` was undefined, and the
        page rendered "No jobs found" no matter how many jobs existed.
        """
        db.add(Job(id=MAIN_JOB_ID, user_id=ALICE_ID, job_type="MAIN",
                   name="report.pdf", created_at=datetime(2026, 1, 1)))
        db.commit()
        fake_redis.add_job_to_user(ALICE_ID, MAIN_JOB_ID)
        fake_redis.set_job_status(job_id=MAIN_JOB_ID, job_type="main",
                                  status="completed", progress=100)

        response = _request(app, "GET", "/jobs", "limit=20&offset=0&job_type=main")
        assert response.status_code == 200
        body = response.json()

        assert isinstance(body, dict), "an envelope, never a bare array"
        assert set(body) >= {"total", "limit", "offset", "jobs"}
        assert isinstance(body["jobs"], list)

        # `total` is the filtered count *before* pagination - it, not
        # len(jobs), is what the pager must divide by PAGE_SIZE.
        assert body["total"] == 1
        assert body["limit"] == 20
        assert body["offset"] == 0

        job = body["jobs"][0]
        # Exactly the fields the job cards read.
        assert set(job) >= {"job_id", "type", "status", "progress", "name",
                            "created_at", "completed_at"}
        assert job["job_id"] == MAIN_JOB_ID

    def test_search_answers_hits_not_jobs(self, app, monkeypatch):
        """
        P0-3b, and the decision behind it.

        A search hit is a match inside indexed content, not a job: it carries
        the evidence (`preview`) and no live job state. The frontend used to
        render search results with the job-card template - `status`, `progress`,
        `name` - all of which are absent here. Rather than make the server
        synthesize job state per hit (a Redis round trip each, and every
        document whose Redis key had expired would vanish from search - i.e.
        precisely the old documents search exists to find), the frontend now
        renders hits as hits. This test pins that decision from the server side.
        """
        class FakeES:
            def search_jobs(self, query, user_id, limit):
                return [{
                    "job_id": MAIN_JOB_ID,
                    "filename": "report.pdf",
                    "total_pages": 3,
                    "char_count": 4200,
                    "created_at": "2026-01-01T00:00:00",
                    "markdown_content": "quarterly invoice totals " * 20,
                }]

        monkeypatch.setattr(routes, "get_es_client", lambda: FakeES())

        response = _request(app, "GET", "/search", "query=invoice&limit=10")
        assert response.status_code == 200
        body = response.json()

        assert set(body) >= {"query", "total", "limit", "results"}
        hit = body["results"][0]
        assert set(hit) >= {"job_id", "filename", "total_pages", "char_count",
                            "created_at", "preview"}
        assert hit["preview"], "the snippet is the point of a search result"

        # If these ever appear, the frontend may go back to the job-card render
        # - but that is a decision, not an accident, so make it fail loudly.
        assert not {"status", "progress", "name"} & set(hit), (
            "search hits deliberately carry no job state; see the docstring"
        )

    def test_page_retry_returns_new_page_job_id(self, app, db, fake_redis,
                                                monkeypatch, tmp_path):
        """
        P0-4's second half. The client read `data.new_job_id`, which the server
        has never returned; the field is `new_page_job_id`.
        """
        db.add(Job(id=MAIN_JOB_ID, user_id=ALICE_ID, job_type="MAIN"))
        db.add(Page(id=str(uuid.uuid4()), job_id=MAIN_JOB_ID, page_number=7,
                    page_job_id="old-page-job", status=DBJobStatus.FAILED,
                    error_message="boom", retry_count=0))
        db.commit()

        # The handler looks for the original upload on disk and enqueues Celery.
        upload_dir = tmp_path / "uploads" / MAIN_JOB_ID
        upload_dir.mkdir(parents=True)
        (upload_dir / "doc.pdf").write_bytes(b"%PDF-1.4\n")

        settings = routes.get_settings()
        monkeypatch.setattr(settings, "temp_storage_path", str(tmp_path))

        enqueued = []
        import workers.tasks as tasks
        monkeypatch.setattr(tasks.process_page, "delay",
                            lambda **kw: enqueued.append(kw))

        response = _request(
            app, "POST", f"/jobs/{MAIN_JOB_ID}/pages/7/retry")
        assert response.status_code == 200, response.body
        body = response.json()

        assert "new_page_job_id" in body, (
            "the frontend reads new_page_job_id; new_job_id has never existed"
        )
        assert body["new_page_job_id"]
        assert body["new_page_job_id"] != "old-page-job"
        assert body["job_id"] == MAIN_JOB_ID
        assert body["page_number"] == 7
        assert enqueued and enqueued[0]["page_number"] == 7

    def test_job_status_survives_the_split_window(self, app, db, fake_redis):
        """
        P0-7. `total_pages` is published to Redis and MySQL *before* the loop
        that inserts the page rows one commit at a time, so there is a real
        window - one that grows with the page count - where the API knows the
        page count but not the page job ids. It used to fill that gap with
        'pending-3', which failed `job_id: UUID` validation and became a 500.
        """
        db.add(Job(id=MAIN_JOB_ID, user_id=ALICE_ID, job_type="MAIN",
                   total_pages=4, created_at=datetime(2026, 1, 1)))
        # Only the first page row exists yet, and it has no page job id either.
        db.add(Page(id=str(uuid.uuid4()), job_id=MAIN_JOB_ID, page_number=1,
                    page_job_id=None, status=DBJobStatus.PENDING))
        db.commit()
        fake_redis.set_job_status(job_id=MAIN_JOB_ID, job_type="main",
                                  status="processing", progress=10)
        fake_redis.set_job_pages(MAIN_JOB_ID, 4)

        response = _request(app, "GET", f"/jobs/{MAIN_JOB_ID}")
        assert response.status_code == 200, (
            f"regression: {response.status_code} during the split window "
            f"-> {response.body!r}"
        )

        pages = response.json()["pages"]
        assert len(pages) == 4
        # Nothing fabricated: a page with no job says so.
        assert all(p["job_id"] is None for p in pages), [p["job_id"] for p in pages]
        # ...and still points at a route that exists.
        for page in pages:
            assert page["url"] == (
                f"/jobs/{MAIN_JOB_ID}/pages/{page['page_number']}/result"
            )

    def test_job_pages_survives_the_split_window(self, app, db, fake_redis):
        """Same placeholder, second endpoint: GET /jobs/{job_id}/pages."""
        db.add(Job(id=MAIN_JOB_ID, user_id=ALICE_ID, job_type="MAIN",
                   total_pages=2))
        db.add(Page(id=str(uuid.uuid4()), job_id=MAIN_JOB_ID, page_number=1,
                    page_job_id=None, status=DBJobStatus.PENDING))
        db.add(Page(id=str(uuid.uuid4()), job_id=MAIN_JOB_ID, page_number=2,
                    page_job_id="22222222-2222-4222-8222-222222222222",
                    status=DBJobStatus.COMPLETED))
        db.commit()

        response = _request(app, "GET", f"/jobs/{MAIN_JOB_ID}/pages")
        assert response.status_code == 200, response.body

        by_number = {p["page_number"]: p for p in response.json()["pages"]}
        assert by_number[1]["job_id"] is None
        assert by_number[1]["url"] == f"/jobs/{MAIN_JOB_ID}/pages/1/result"
        assert by_number[2]["job_id"] == "22222222-2222-4222-8222-222222222222"
        assert by_number[2]["url"] == (
            "/jobs/22222222-2222-4222-8222-222222222222/result"
        )
