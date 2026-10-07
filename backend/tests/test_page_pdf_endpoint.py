"""
Tests for GET /jobs/{job_id}/pages/{page_number}/pdf.

This endpoint used to be deliberately unauthenticated and 307-redirected to a
public MinIO URL: anyone holding (or guessing) a job UUID could read another
user's page PDF, and the object was anonymously readable anyway because the
bucket carried a `s3:GetObject` policy for `Principal: *`.

What is pinned here:
  - authorization goes through `api.deps.get_owned_job` (MySQL as the source of
    truth, 404 - never 403 - for someone else's job, so nothing is enumerable);
  - the response is JSON carrying a presigned URL plus its expiry, not a
    redirect (a redirect cannot carry the caller's Authorization header, and the
    frontend needs to know when the URL dies);
  - the URL is signed for a short, deliberate TTL.

No live MinIO/Redis/MySQL: SQLite with the real models, and a fake MinIO client.
Requests go through the real FastAPI app (so the declared dependencies, and
therefore the authentication, are actually exercised) over a minimal in-process
ASGI call - `fastapi.testclient` is deliberately avoided because it drags in an
HTTP client that is not needed to talk to an app living in the same process.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database import Base, get_db
from shared.models import Job, Page, User
from shared.auth import get_current_active_user

import api.routes as routes


DEFAULT_HOST = "localhost:8000"

PAGE_OBJECT = "pages/job-1/page_0001.pdf"
SIGNED_URL = (
    "http://127.0.0.1:9000/ingestify-pages/pages/job-1/page_0001.pdf"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=deadbeef"
)


class FakeMinIO:
    """Stands in for MinIOClient: records calls, never touches the network."""

    def __init__(self, exists=True):
        self.bucket_pages = "ingestify-pages"
        self._exists = exists
        self.presign_calls = []

    def file_exists(self, bucket_name, object_name):
        return self._exists

    def get_presigned_url(self, bucket_name, object_name, expires=None, request_host=None):
        self.presign_calls.append(
            {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "expires": expires,
                "request_host": request_host,
            }
        )
        return SIGNED_URL


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    """Redis must never be what authorizes a request in these tests."""
    monkeypatch.setattr("api.deps._redis_job_status", lambda job_id: None)
    monkeypatch.setattr("api.deps._redis_owner_matches", lambda job_id, user_id: False)


@pytest.fixture
def minio(monkeypatch):
    fake = FakeMinIO()
    monkeypatch.setattr(routes, "get_minio_client", lambda: fake)
    return fake


@pytest.fixture
def users(db):
    alice = User(id="user-alice", email="alice@example.com", username="alice",
                 hashed_password="x")
    mallory = User(id="user-mallory", email="mallory@example.com", username="mallory",
                   hashed_password="x")
    db.add_all([alice, mallory])
    db.commit()
    return alice, mallory


@pytest.fixture
def app(db):
    application = FastAPI()
    application.include_router(routes.router)
    application.dependency_overrides[get_db] = lambda: db
    return application


class Response:
    """The bits of an HTTP response these tests care about."""

    def __init__(self, status, headers, body):
        self.status_code = status
        self.headers = {k.decode().lower(): v.decode() for k, v in headers}
        self.body = body

    def json(self):
        return json.loads(self.body)


def _get(app, path, user=None, host=DEFAULT_HOST):
    """GET `path` through the ASGI app, optionally as an authenticated `user`."""
    if user is not None:
        app.dependency_overrides[get_current_active_user] = lambda: user

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", host.encode())],
        "client": ("127.0.0.1", 51234),
        "server": tuple(host.split(":")[:1]) + (8000,),
    }

    messages = []

    async def receive():
        # StreamingResponse listens for disconnects concurrently; yield control
        # until its body completes instead of spinning on repeated requests.
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))

    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return Response(start["status"], start["headers"], body)


def _job_with_page(db, job_id="job-1", user_id="user-alice", page_number=1,
                   minio_page_path=PAGE_OBJECT):
    db.add(Job(id=job_id, user_id=user_id, job_type="MAIN"))
    db.add(Page(job_id=job_id, page_number=page_number,
                minio_page_path=minio_page_path))
    db.commit()


class TestAuthorization:
    def test_anonymous_is_rejected(self, app, db, users, minio):
        """The old endpoint served this to anyone. It must now demand credentials."""
        _job_with_page(db)
        response = _get(app, "/jobs/job-1/pages/1/pdf")
        assert response.status_code == 401
        assert minio.presign_calls == []

    def test_owner_gets_a_url(self, app, db, users, minio):
        alice, _ = users
        _job_with_page(db, user_id=alice.id)
        response = _get(app, "/jobs/job-1/pages/1/pdf", alice)
        assert response.status_code == 200
        assert response.json()["url"] == SIGNED_URL

    def test_other_user_gets_404_not_403(self, app, db, users, minio):
        """404 with the shared message: a 403 would confirm the job exists."""
        alice, mallory = users
        _job_with_page(db, user_id=alice.id)
        response = _get(app, "/jobs/job-1/pages/1/pdf", mallory)
        assert response.status_code == 404
        assert response.json()["detail"] == "Job não encontrado"
        assert minio.presign_calls == []

    def test_orphan_job_authorizes_nobody(self, app, db, users, minio):
        """`Job.user_id` is nullable (ondelete=SET NULL); absent owner != public."""
        alice, _ = users
        _job_with_page(db, user_id=None)
        response = _get(app, "/jobs/job-1/pages/1/pdf", alice)
        assert response.status_code == 404
        assert minio.presign_calls == []

    def test_unknown_job_is_404(self, app, db, users, minio):
        alice, _ = users
        response = _get(app, "/jobs/does-not-exist/pages/1/pdf", alice)
        assert response.status_code == 404
        assert minio.presign_calls == []


class TestResponseShape:
    def test_returns_json_not_a_redirect(self, app, db, users, minio):
        alice, _ = users
        _job_with_page(db, user_id=alice.id)
        response = _get(app, "/jobs/job-1/pages/1/pdf", alice)

        assert response.status_code == 200
        assert "location" not in response.headers
        assert response.headers["content-type"].startswith("application/json")

    def test_payload_carries_url_and_expiry(self, app, db, users, minio):
        alice, _ = users
        _job_with_page(db, user_id=alice.id)

        before = datetime.now(timezone.utc)
        body = _get(app, "/jobs/job-1/pages/1/pdf", alice).json()
        after = datetime.now(timezone.utc)

        assert body["job_id"] == "job-1"
        assert body["page_number"] == 1
        assert body["url"] == SIGNED_URL
        assert body["preview_url"] == "http://localhost:8000/jobs/job-1/pages/1/pdf/content"
        assert body["expires_in"] == routes.PAGE_PDF_URL_TTL_SECONDS

        expires_at = datetime.fromisoformat(body["expires_at"])
        assert expires_at.tzinfo is not None, "expires_at must be unambiguous (UTC)"
        ttl = timedelta(seconds=routes.PAGE_PDF_URL_TTL_SECONDS)
        assert before + ttl <= expires_at <= after + ttl

    def test_ttl_is_short(self, app, db, users, minio):
        """Deliberate window: long enough to load and read a page, short enough
        that a leaked URL is worthless quickly."""
        alice, _ = users
        _job_with_page(db, user_id=alice.id)
        _get(app, "/jobs/job-1/pages/1/pdf", alice)

        assert routes.PAGE_PDF_URL_TTL_SECONDS == 15 * 60
        assert minio.presign_calls[0]["expires"] == timedelta(
            seconds=routes.PAGE_PDF_URL_TTL_SECONDS
        )

    def test_signs_for_the_host_the_caller_used(self, app, db, users, minio):
        """The SigV4 signature covers the Host header, so the request host has
        to reach the signer - otherwise every PDF 403s in the browser."""
        alice, _ = users
        _job_with_page(db, user_id=alice.id)

        _get(app, "/jobs/job-1/pages/1/pdf", alice, host="192.168.1.10:8000")

        assert minio.presign_calls[0]["request_host"] == "192.168.1.10:8000"
        assert minio.presign_calls[0]["bucket_name"] == "ingestify-pages"
        assert minio.presign_calls[0]["object_name"] == PAGE_OBJECT


class TestObjectResolution:
    def test_falls_back_to_the_conventional_path(self, app, db, users, minio):
        alice, _ = users
        _job_with_page(db, user_id=alice.id, page_number=5, minio_page_path=None)

        _get(app, "/jobs/job-1/pages/5/pdf", alice)

        assert minio.presign_calls[0]["object_name"] == "pages/job-1/page_0005.pdf"

    def test_missing_page_row_is_404(self, app, db, users, minio):
        alice, _ = users
        db.add(Job(id="job-1", user_id=alice.id, job_type="MAIN"))
        db.commit()

        response = _get(app, "/jobs/job-1/pages/9/pdf", alice)
        assert response.status_code == 404
        assert minio.presign_calls == []

    def test_object_missing_in_minio_is_404(self, app, db, users, monkeypatch):
        alice, _ = users
        _job_with_page(db, user_id=alice.id)
        fake = FakeMinIO(exists=False)
        monkeypatch.setattr(routes, "get_minio_client", lambda: fake)

        response = _get(app, "/jobs/job-1/pages/1/pdf", alice)
        assert response.status_code == 404
        assert fake.presign_calls == []


class TestAuthenticatedPreview:
    def test_owner_can_preview_before_conversion_finishes(self, app, db, users, minio):
        alice, _ = users
        _job_with_page(db, user_id=alice.id)  # PENDING page
        source = MagicMock()
        source.stream.return_value = iter([b"%PDF-1.4\n", b"preview"])
        minio.open_object = MagicMock(return_value=source)
        response = _get(app, "/jobs/job-1/pages/1/pdf/content", alice)
        assert response.status_code == 200
        assert response.body == b"%PDF-1.4\npreview"
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["cache-control"] == "private, no-store"
        minio.open_object.assert_called_once_with("ingestify-pages", PAGE_OBJECT)
        source.close.assert_called_once()
        source.release_conn.assert_called_once()

    @pytest.mark.parametrize("as_other_user", [False, True])
    def test_preview_requires_the_owner(self, app, db, users, minio, as_other_user):
        alice, mallory = users
        _job_with_page(db, user_id=alice.id)
        minio.open_object = MagicMock()
        response = _get(app, "/jobs/job-1/pages/1/pdf/content", mallory if as_other_user else None)
        assert response.status_code == (404 if as_other_user else 401)
        minio.open_object.assert_not_called()

    def test_missing_preview_object_returns_404(self, app, db, users, monkeypatch):
        alice, _ = users
        _job_with_page(db, user_id=alice.id)
        monkeypatch.setattr(routes, "get_minio_client", lambda: FakeMinIO(exists=False))
        assert _get(app, "/jobs/job-1/pages/1/pdf/content", alice).status_code == 404
