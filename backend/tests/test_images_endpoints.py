"""
The vision endpoints: POST /images/describe, POST /images/ocr and their
multipart siblings.

Why this file exists
--------------------
Three things about these routes are easy to get wrong and impossible to notice
from the outside:

  1. **They must not be anonymous.** The page-PDF route shipped unauthenticated
     and had to be closed as a security finding; these are the next endpoints
     that take a body and do expensive work, and "it worked in curl" is exactly
     how an endpoint ends up public. Every route here is exercised without
     credentials, and the assertion is not only the 401 - it is that *nothing
     happened*: no job row, no dispatch.

  2. **Validation has to come before the model.** Size, base64 and format are
     checked in the API, on the bytes, before a job exists and before anything
     is enqueued. A payload that is not an image must never reach a worker
     holding a half-gigabyte of weights, and the caller must get a code
     (`INVALID_BASE64`, `IMAGE_TOO_LARGE`, `UNSUPPORTED_IMAGE_FORMAT`) rather
     than a stack trace.

  3. **Unavailability is a contract, not an accident.** No torch, no weights,
     flag off, no worker: each is a 503 with an actionable message, and the
     structured failure the task *returns* (rather than raises) has to survive
     the trip and become the status the caller sees.

Plus the two properties the whole synchronous design rests on: the echoed
`image_base64` is byte-identical to what was sent, and a 504 is not a lost
request - the job is created and owned *before* dispatch, so `job_id` and
`poll_url` in the timeout body actually lead somewhere.

What is mocked
--------------
Everything below the API: no model, no torch, no GPU, no network, no Celery.
`_dispatch_vision_task` is the seam - it is replaced with a fake that records
its kwargs and answers with a canned payload, which is also what lets the
timeout and failure paths be tested in milliseconds. Storage is a fake MinIO
plus a tmp_path; Redis is fakeredis through the real RedisClient; MySQL is
SQLite with the real models.

Requests go through the real FastAPI app in-process (so the declared
dependencies, and therefore the authentication, are actually exercised) over a
minimal ASGI call. `fastapi.testclient` is deliberately avoided, following
`test_page_pdf_endpoint.py` - which is also where the ASGI helper came from,
extended here to carry a request body, since every existing helper hardcodes
`body=b""`.
"""

import asyncio
import base64
import json
import time

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database import Base, get_db
from shared.models import Job, User
from shared.auth import get_current_active_user
from shared.schemas import VisionCapabilitiesResponse

import api.image_routes as image_routes


DEFAULT_HOST = "localhost:8000"

# A real 1x1 PNG. The API never decodes an image (that is the worker's job and
# the reason PIL is not an API dependency), but a fixture that is a genuine
# file keeps the magic-byte check honest.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")

MODEL_INFO = {
    "model_id": "florence-community/Florence-2-base-ft",
    "revision": "0b03b6f15a4a211370fb204aee4e7dd48887ea37",
    "device": "cpu",
    "dtype": "float32",
}

DESCRIBE_PAYLOAD = {
    "ok": True,
    "description": "Um quadrado azul de um pixel sobre fundo branco.",
    "task": "<MORE_DETAILED_CAPTION>",
    "width": 1,
    "height": 1,
    "duration_ms": 1234,
    "model": MODEL_INFO,
}

OCR_PAYLOAD = {
    "ok": True,
    "text": "INGESTIFY\nnota fiscal",
    "lines": [
        {
            "text": "INGESTIFY",
            "quad_box": [10.0, 12.0, 90.5, 12.0, 90.5, 30.25, 10.0, 30.25],
            "bbox": [10.0, 12.0, 90.5, 30.25],
        },
        {
            "text": "nota fiscal",
            "quad_box": [10.0, 40.0, 70.0, 40.0, 70.0, 55.0, 10.0, 55.0],
            "bbox": [10.0, 40.0, 70.0, 55.0],
        },
    ],
    "width": 200,
    "height": 100,
    "duration_ms": 4321,
    "model": MODEL_INFO,
}


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

class FakeAsyncResult:
    """The three members of `celery.result.AsyncResult` the route touches."""

    def __init__(self, result=None, ready=True, task_id="task-1"):
        self.id = task_id
        self._result = result
        self._ready = ready

    def ready(self):
        return self._ready

    @property
    def result(self):
        return self._result


class FakeDispatch:
    """Replaces `_dispatch_vision_task`: records calls, answers with a canned result."""

    def __init__(self, result=None, ready=True, raises=None):
        self.calls = []
        self._result = result
        self._ready = ready
        self._raises = raises

    def __call__(self, kind, **kwargs):
        self.calls.append({"kind": kind, **kwargs})
        if self._raises is not None:
            raise self._raises
        return FakeAsyncResult(self._result, ready=self._ready)


class FakeMinIO:
    """Stands in for MinIOClient: records uploads, never touches the network.

    Kept even though `/images/*` no longer writes to object storage - it is the
    trap. It is installed with `raising=False`, so re-adding a
    `get_minio_client` import to the route rebinds it to this recorder instead
    of to a client that would open a socket, and
    `test_the_image_is_not_copied_to_object_storage` sees the write.
    """

    def __init__(self, fail=False):
        self.bucket_uploads = "ingestify-uploads"
        self.uploads = []
        self._fail = fail

    def upload_file(self, bucket_name, object_name, file_data=None, content_type=None, **kw):
        if self._fail:
            raise RuntimeError("MinIO is down")
        self.uploads.append(
            {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "size": len(file_data or b""),
                "content_type": content_type,
            }
        )
        return object_name


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def no_redis(monkeypatch, fake_redis):
    """Redis is fakeredis through the real client - never a live server."""
    monkeypatch.setattr(image_routes, "get_redis_client", lambda: fake_redis)
    return fake_redis


@pytest.fixture(autouse=True)
def minio(monkeypatch):
    """A recorder bound wherever a bucket write could come from.

    Both bindings matter, and only having the first is how the first draft of
    this fixture let a reintroduced upload through: the route no longer has a
    `get_minio_client` name (hence `raising=False`), so a re-added upload
    written as a function-local `from shared.minio_client import ...` would
    have resolved past the module attribute and reached a real client. Patching
    the source module as well closes that, and keeps the suite off the network
    either way.
    """
    import shared.minio_client as minio_module

    fake = FakeMinIO()
    monkeypatch.setattr(image_routes, "get_minio_client", lambda: fake, raising=False)
    monkeypatch.setattr(minio_module, "get_minio_client", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def temp_storage(monkeypatch, tmp_path):
    """The image handoff writes to disk; keep it inside the test's tmp_path."""
    monkeypatch.setattr(image_routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(image_routes.settings, "enable_image_description", True)
    return tmp_path


@pytest.fixture
def dispatch(monkeypatch):
    """Default seam: describe succeeds. Individual tests install their own."""
    fake = FakeDispatch(result=DESCRIBE_PAYLOAD)
    monkeypatch.setattr(image_routes, "_dispatch_vision_task", fake)
    return fake


@pytest.fixture
def install_dispatch(monkeypatch):
    def install(**kwargs):
        fake = FakeDispatch(**kwargs)
        monkeypatch.setattr(image_routes, "_dispatch_vision_task", fake)
        return fake

    return install


@pytest.fixture
def users(db):
    alice = User(id="user-alice", email="alice@example.com", username="alice",
                 hashed_password="x")
    db.add(alice)
    db.commit()
    return alice


@pytest.fixture
def app(db):
    application = FastAPI()
    application.include_router(image_routes.router)
    application.dependency_overrides[get_db] = lambda: db
    return application


# ---------------------------------------------------------------------------
# Minimal in-process ASGI call, with a body
# ---------------------------------------------------------------------------

class Response:
    def __init__(self, status, headers, body):
        self.status_code = status
        self.headers = {k.decode().lower(): v.decode() for k, v in headers}
        self.body = body

    def json(self):
        return json.loads(self.body)

    @property
    def detail(self):
        """The `{"error_code", "message", "job_id"}` envelope of a failure."""
        return self.json()["detail"]


def _request(app, method, path, user=None, body=b"", content_type=None, host=DEFAULT_HOST):
    """
    Call `app` directly. `user`, when given, satisfies the auth dependency.

    The existing helpers in this suite send `body=b""` and no content-type,
    which cannot express a JSON or multipart POST at all; this one carries
    both, and is otherwise the same call.
    """
    if user is not None:
        app.dependency_overrides[get_current_active_user] = lambda: user

    headers = [(b"host", host.encode())]
    if content_type is not None:
        headers.append((b"content-type", content_type.encode()))
    headers.append((b"content-length", str(len(body)).encode()))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 51234),
        "server": tuple(host.split(":")[:1]) + (8000,),
    }

    messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))

    start = next(m for m in messages if m["type"] == "http.response.start")
    payload = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return Response(start["status"], start["headers"], payload)


def _post_json(app, path, payload, user=None):
    return _request(
        app,
        "POST",
        path,
        user=user,
        body=json.dumps(payload).encode(),
        content_type="application/json",
    )


MULTIPART_BOUNDARY = "----ingestifyTestBoundary"


def _multipart(fields, file_field=None):
    """Build a multipart/form-data body: `fields` are text, `file_field` is bytes."""
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{MULTIPART_BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    if file_field is not None:
        name, filename, content, content_type = file_field
        parts.append(
            f"--{MULTIPART_BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n".encode()
            + content
            + b"\r\n"
        )
    parts.append(f"--{MULTIPART_BOUNDARY}--\r\n".encode())
    return b"".join(parts)


def _post_multipart(app, path, fields=None, file_field=None, user=None):
    return _request(
        app,
        "POST",
        path,
        user=user,
        body=_multipart(fields or {}, file_field),
        content_type=f"multipart/form-data; boundary={MULTIPART_BOUNDARY}",
    )


def _png_upload(filename="foto.png"):
    return ("file", filename, PNG_BYTES, "image/png")


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

class TestAuthorization:
    """
    These endpoints are expensive and they take a body. A public one was just
    closed as a security finding; none of these may be anonymous.
    """

    @pytest.mark.parametrize(
        "path,payload",
        [
            ("/images/describe", {"image_base64": PNG_B64}),
            ("/images/ocr", {"image_base64": PNG_B64}),
        ],
    )
    def test_anonymous_json_is_rejected(self, app, db, users, dispatch, path, payload):
        response = _post_json(app, path, payload)

        assert response.status_code == 401
        assert dispatch.calls == [], "an unauthenticated request must not reach a worker"
        assert db.query(Job).count() == 0, "nor create a job"

    @pytest.mark.parametrize("path", ["/images/describe/upload", "/images/ocr/upload"])
    def test_anonymous_multipart_is_rejected(self, app, db, users, dispatch, path):
        response = _post_multipart(app, path, file_field=_png_upload())

        assert response.status_code == 401
        assert dispatch.calls == []
        assert db.query(Job).count() == 0

    def test_anonymous_capabilities_is_rejected(self, app, users, monkeypatch):
        """It discloses model ids, revisions and hardware - not an open probe."""
        probed = []
        monkeypatch.setattr(
            image_routes,
            "_read_capabilities_heartbeat",
            lambda: probed.append(1) or None,
        )

        response = _request(app, "GET", "/images/capabilities")

        assert response.status_code == 401
        assert probed == []

    def test_the_job_is_owned_by_the_caller(self, app, db, users, dispatch):
        """
        Ownership is written before dispatch, which is what makes
        `/jobs/{job_id}` work on a vision job with no special case - and what
        makes the 504 fallback reachable.
        """
        _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        job = db.query(Job).one()
        assert job.user_id == users.id
        assert job.source_type == "image"
        assert job.job_type == "MAIN"


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

class TestDescribeHappyPath:
    def test_json_base64_returns_the_description(self, app, db, users, dispatch):
        response = _post_json(
            app, "/images/describe", {"image_base64": PNG_B64, "filename": "foto.png"},
            user=users,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["description"] == DESCRIBE_PAYLOAD["description"]
        assert body["status"] == "completed"
        assert body["task"] == "<MORE_DETAILED_CAPTION>"
        assert body["width"] == 1 and body["height"] == 1
        assert body["duration_ms"] == 1234
        assert body["model"] == MODEL_INFO
        assert body["job_id"] == db.query(Job).one().id

    def test_the_echoed_image_is_byte_identical(self, app, db, users, dispatch):
        """
        The API keeps the caller's bytes in memory and re-encodes those; it
        never round-trips them through the worker or through PIL, so this is
        identity, not "close enough after a re-compress".
        """
        response = _post_json(
            app, "/images/describe", {"image_base64": PNG_B64}, user=users
        )

        body = response.json()
        assert base64.b64decode(body["image_base64"]) == PNG_BYTES
        assert body["image_mime_type"] == "image/png"
        assert body["image_bytes"] == len(PNG_BYTES)
        assert len(body["image_sha256"]) == 64

    def test_line_wrapped_base64_is_accepted(self, app, db, users, dispatch):
        """
        MIME-style base64 wraps at 64/76 columns, and that is what every
        command-line encoder produces: `base64 foto.png`, `openssl base64`,
        Python's `base64.encodebytes`, Java's `Base64.getMimeEncoder()`.

        `b64decode(validate=True)` rejects the newlines, so a caller who pasted
        the output of any of those was told their perfectly valid base64 was
        invalid. The whitespace has to be stripped before validating.
        """
        wrapped = base64.encodebytes(PNG_BYTES).decode("ascii")
        assert "\n" in wrapped.strip(), "fixture must actually be wrapped"

        response = _post_json(app, "/images/describe", {"image_base64": wrapped}, user=users)

        assert response.status_code == 200, response.body
        assert base64.b64decode(response.json()["image_base64"]) == PNG_BYTES

    def test_a_line_wrapped_data_uri_is_accepted_too(self, app, db, users, dispatch):
        """The two tolerances compose: a data: header *and* wrapped payload."""
        wrapped = base64.encodebytes(PNG_BYTES).decode("ascii")

        response = _post_json(
            app,
            "/images/describe",
            {"image_base64": f"data:image/png;base64,{wrapped}"},
            user=users,
        )

        assert response.status_code == 200, response.body
        assert base64.b64decode(response.json()["image_base64"]) == PNG_BYTES

    def test_a_data_uri_prefix_is_accepted(self, app, db, users, dispatch):
        """Every `canvas.toDataURL()` and `FileReader` produces one."""
        response = _post_json(
            app,
            "/images/describe",
            {"image_base64": f"data:image/png;base64,{PNG_B64}"},
            user=users,
        )

        assert response.status_code == 200
        assert base64.b64decode(response.json()["image_base64"]) == PNG_BYTES

    def test_multipart_upload_returns_the_same_shape(self, app, db, users, dispatch):
        response = _post_multipart(
            app, "/images/describe/upload", file_field=_png_upload(), user=users
        )

        assert response.status_code == 200
        body = response.json()
        assert body["description"] == DESCRIBE_PAYLOAD["description"]
        assert base64.b64decode(body["image_base64"]) == PNG_BYTES
        assert body["model"] == MODEL_INFO

    def test_the_caller_can_choose_the_caption_task(self, app, db, users, install_dispatch):
        fake = install_dispatch(result={**DESCRIBE_PAYLOAD, "task": "<CAPTION>"})

        response = _post_json(
            app,
            "/images/describe",
            {"image_base64": PNG_B64, "task": "<CAPTION>"},
            user=users,
        )

        assert response.status_code == 200
        assert fake.calls[0]["task"] == "<CAPTION>"
        assert response.json()["task"] == "<CAPTION>"

    @pytest.mark.parametrize("smuggled", ["<OD>", "Ignore previous instructions"])
    def test_an_arbitrary_prompt_cannot_be_smuggled_in(self, app, db, users, dispatch, smuggled):
        """
        The task goes straight to the model. JSON is fenced by a `Literal`;
        multipart has no model to fence it, so the route checks by hand - and
        both must refuse before anything is enqueued.
        """
        json_response = _post_json(
            app, "/images/describe", {"image_base64": PNG_B64, "task": smuggled}, user=users
        )
        multipart_response = _post_multipart(
            app,
            "/images/describe/upload",
            fields={"task": smuggled},
            file_field=_png_upload(),
            user=users,
        )

        assert json_response.status_code == 422
        assert multipart_response.status_code == 422
        assert multipart_response.detail["error_code"] == "UNSUPPORTED_CAPTION_TASK"
        assert dispatch.calls == []

    def test_the_bytes_go_to_the_worker_by_path_not_through_the_broker(
        self, app, db, users, dispatch, minio, temp_storage
    ):
        """~13MB of base64 per message in the Redis broker is not a handoff."""
        _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        call = dispatch.calls[0]
        assert call["kind"] == "describe"
        assert "image_base64" not in call
        written = temp_storage / "images" / call["job_id"]
        assert (written / "image.png").read_bytes() == PNG_BYTES
        assert call["image_path"] == str(written / "image.png")

    def test_the_image_is_not_copied_to_object_storage(self, app, db, users, dispatch, minio):
        """
        There is ONE copy of the image, on the shared volume, and it is the one
        the worker reads.

        The route used to also PUT `images/{job_id}/{filename}` into the uploads
        bucket under the name "retention". Nothing ever read it: the worker
        reads the disk, the response echoes the bytes back inline, and
        `/jobs/{id}/result` returns the inference JSON. Nothing even *pointed*
        at it - unlike `/upload` and `/transcribe`, the object name was never
        written to `Job.minio_upload_path` - so it could be neither served nor
        swept, and it had no TTL. That is not retention, it is an unbounded,
        unreferenceable leak with a 10MB PUT on the hot path of a synchronous
        request. A second copy that no one reads has no correct lifetime except
        "never created".
        """
        _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert minio.uploads == []
        job = db.query(Job).one()
        assert job.minio_upload_path is None

    def test_a_caller_supplied_filename_cannot_escape_its_directory(
        self, app, db, users, dispatch, temp_storage
    ):
        _post_json(
            app,
            "/images/describe",
            {"image_base64": PNG_B64, "filename": "../../../etc/cron.d/pwn"},
            user=users,
        )

        image_path = dispatch.calls[0]["image_path"]
        assert image_path.endswith("/pwn")
        assert str(temp_storage) in image_path


class TestOcrHappyPath:
    def test_json_base64_returns_text_and_regions(self, app, db, users, install_dispatch):
        install_dispatch(result=OCR_PAYLOAD)

        response = _post_json(app, "/images/ocr", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "INGESTIFY\nnota fiscal"
        assert len(body["lines"]) == 2
        assert body["lines"][0]["text"] == "INGESTIFY"
        assert body["lines"][0]["quad_box"] == [10.0, 12.0, 90.5, 12.0, 90.5, 30.25, 10.0, 30.25]
        assert body["lines"][0]["bbox"] == [10.0, 12.0, 90.5, 30.25]
        assert body["width"] == 200 and body["height"] == 100
        assert base64.b64decode(body["image_base64"]) == PNG_BYTES

    def test_multipart_upload_returns_the_same_shape(self, app, db, users, install_dispatch):
        install_dispatch(result=OCR_PAYLOAD)

        response = _post_multipart(
            app, "/images/ocr/upload", file_field=_png_upload(), user=users
        )

        assert response.status_code == 200
        assert response.json()["text"] == "INGESTIFY\nnota fiscal"

    def test_an_image_with_no_text_is_a_200_not_an_error(self, app, db, users, install_dispatch):
        """"Nothing found" is a result. A 4xx here would make callers retry."""
        install_dispatch(result={**OCR_PAYLOAD, "text": "", "lines": []})

        response = _post_json(app, "/images/ocr", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 200
        assert response.json()["text"] == ""
        assert response.json()["lines"] == []

    def test_ocr_takes_no_task_from_the_caller(self, app, db, users, install_dispatch):
        """`<OCR_WITH_REGION>` is the endpoint's identity, not a parameter."""
        fake = install_dispatch(result=OCR_PAYLOAD)

        _post_json(app, "/images/ocr", {"image_base64": PNG_B64, "task": "<CAPTION>"}, user=users)

        assert "task" not in fake.calls[0]


# ---------------------------------------------------------------------------
# The route and the task have to agree - and nothing else in this file checks
# ---------------------------------------------------------------------------

@pytest.fixture
def eager_vision(monkeypatch, fake_redis):
    """
    Run the REAL Celery task in-process, backed by the stub provider.

    This is the one seam in this file that does NOT replace
    `_dispatch_vision_task`. Everywhere else the task contract is written down
    twice - once in `workers/vision_tasks.py` and once in `DESCRIBE_PAYLOAD` /
    `OCR_PAYLOAD` - and nothing forces the two copies to agree. Renaming the
    `image_path` kwarg, or the `description` key of the returned payload, would
    500 every `/images/*` request in production while every mocked test here
    stayed green.

    So: Celery in eager mode (the task runs inline, no broker, no worker),
    `VISION_PROVIDER=stub` (a real ImageDescriber with deterministic output and
    no torch), and fakeredis behind the status/result writes the task performs
    through its own import of `shared.redis_client`. Route, task, factory and
    describer are all real; the assertions are on the HTTP body.
    """
    import shared.redis_client as redis_module
    from shared.config import get_settings
    from workers.celery_app import celery_app
    from workers.vision.factory import reset_image_describer

    # The task imports get_redis_client from the module at call time, so this
    # is the seam that keeps the status/result writes off a live server.
    monkeypatch.setattr(redis_module, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(get_settings(), "vision_provider", "stub")

    previous_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    reset_image_describer()
    try:
        yield fake_redis
    finally:
        celery_app.conf.task_always_eager = previous_eager
        reset_image_describer()


class TestRouteAndTaskAgree:
    """
    End-to-end through the real task: HTTP -> route -> Celery -> vision_tasks
    -> factory -> StubDescriber -> HTTP body.

    The stub's output is derived from the image dimensions, so a 1x1 PNG gives
    exactly one answer and there is no canned payload to drift out of date.
    """

    def test_describe_traverses_the_real_task(self, app, db, users, eager_vision):
        response = _post_json(
            app,
            "/images/describe",
            {"image_base64": PNG_B64, "filename": "foto.png"},
            user=users,
        )

        assert response.status_code == 200, response.body
        body = response.json()
        # Produced by StubDescriber.describe() from the real 1x1 PNG - which is
        # only reachable if the route's kwargs match the task's signature.
        assert body["description"] == "A stub description of a 1x1 image."
        assert body["task"] == "<MORE_DETAILED_CAPTION>"
        assert body["width"] == 1 and body["height"] == 1
        assert body["status"] == "completed"
        assert body["job_id"] == db.query(Job).one().id
        # The factory answered with the configured provider, not another one.
        assert body["model"]["model_id"] == "stub"
        assert body["model"]["revision"] == "stub"
        assert body["model"]["device"] == "cpu"
        assert body["model"]["dtype"] == "float32"
        assert base64.b64decode(body["image_base64"]) == PNG_BYTES

    def test_the_caption_task_reaches_the_describer(self, app, db, users, eager_vision):
        """`task` is the third kwarg of `describe_image_task`; it travels too."""
        response = _post_json(
            app,
            "/images/describe",
            {"image_base64": PNG_B64, "task": "<CAPTION>"},
            user=users,
        )

        assert response.status_code == 200, response.body
        assert response.json()["task"] == "<CAPTION>"

    def test_ocr_traverses_the_real_task(self, app, db, users, eager_vision):
        response = _post_json(app, "/images/ocr", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 200, response.body
        body = response.json()
        assert body["text"] == "stub line one\nstub line two"
        assert [line["text"] for line in body["lines"]] == [
            "stub line one",
            "stub line two",
        ]
        assert len(body["lines"][0]["quad_box"]) == 8
        assert len(body["lines"][0]["bbox"]) == 4
        assert body["model"]["model_id"] == "stub"

    def test_the_task_records_the_job_it_finished(self, app, db, users, eager_vision):
        """
        `_set_status` and `_store_result` are what make the 504-then-poll
        fallback real: without them a timed-out request would find nothing at
        `/jobs/{job_id}/result` even though the task completed.
        """
        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        job_id = response.json()["job_id"]
        assert eager_vision.get_job_status(job_id)["status"] == "completed"
        stored = eager_vision.get_job_result(job_id)
        assert stored["description"] == "A stub description of a 1x1 image."
        assert stored["job_id"] == job_id

    def test_a_describer_failure_travels_back_as_its_own_status(
        self, app, db, users, eager_vision, monkeypatch
    ):
        """
        A typed VisionError is *returned* by the task, not raised, so that it
        survives the Celery JSON result serializer. This drives the real return
        path rather than injecting the dict the API expects to see.
        """
        from workers.vision.errors import VisionModelLoadError
        from workers.vision.stub_describer import StubDescriber

        def boom(self, image_path, options=None):
            raise VisionModelLoadError("the stub refused to load")

        monkeypatch.setattr(StubDescriber, "describe", boom)

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 503
        assert response.detail["error_code"] == "VISION_MODEL_LOAD_FAILED"
        assert "the stub refused to load" in response.detail["message"]
        assert response.detail["job_id"] == db.query(Job).one().id


# ---------------------------------------------------------------------------
# The image does not outlive the work it was uploaded for
# ---------------------------------------------------------------------------

def _handoff_dirs(temp_storage):
    """The per-job directories currently sitting under `<temp>/images`."""
    root = temp_storage / "images"
    return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


class TestTheImageIsDeleted:
    """
    `/images/*` is a synchronous endpoint an authenticated caller can hit in a
    loop, at up to 10MB a time, writing onto a bind-mounted host volume shared
    by the API and every worker. Nothing deleted those bytes: the disk filled
    at the caller's chosen rate.

    The deletion belongs to the TASK, not to the route, and the two halves of
    that sentence both need a test:

      - the task deletes on every exit, not just the happy one, which is why
        the failing and crashing paths are exercised here through the real task
        rather than through a stubbed dispatch;
      - the route must NOT delete when it gives up, because a 504 is a handover
        and the task is still reading the file. `test_a_timed_out_request_leaves
        _the_image_for_the_still_running_task` is what fails if someone
        "improves" this into a `finally` around the request.

    The route cleans up in exactly one situation: the task was never dispatched,
    so nobody else is ever going to.
    """

    def test_the_image_is_deleted_when_the_task_finishes(
        self, app, db, users, eager_vision, temp_storage
    ):
        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 200, response.body
        assert _handoff_dirs(temp_storage) == []

    def test_the_image_is_deleted_when_the_inference_fails(
        self, app, db, users, eager_vision, temp_storage, monkeypatch
    ):
        """A typed failure returns rather than raises - the `finally` must still fire."""
        from workers.vision.errors import VisionModelLoadError
        from workers.vision.stub_describer import StubDescriber

        def boom(self, image_path, options=None):
            raise VisionModelLoadError("the stub refused to load")

        monkeypatch.setattr(StubDescriber, "describe", boom)

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 503
        assert _handoff_dirs(temp_storage) == []

    def test_the_image_is_deleted_when_the_task_crashes(
        self, app, db, users, eager_vision, temp_storage, monkeypatch
    ):
        """An unexpected exception propagates out of the task; cleanup precedes it."""
        from workers.vision.stub_describer import StubDescriber

        def boom(self, image_path, options=None):
            raise RuntimeError("something exploded inside the model")

        monkeypatch.setattr(StubDescriber, "ocr", boom)

        response = _post_json(app, "/images/ocr", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 500
        assert _handoff_dirs(temp_storage) == []

    def test_the_image_is_deleted_when_the_dispatch_never_happens(
        self, app, db, users, install_dispatch, temp_storage
    ):
        """No task was enqueued, so the route is the last one holding the file."""
        install_dispatch(raises=ImportError("no module named workers.vision_tasks"))

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 503
        assert _handoff_dirs(temp_storage) == []

    def test_the_image_is_deleted_when_the_broker_is_down(
        self, app, db, users, install_dispatch, temp_storage
    ):
        install_dispatch(raises=RuntimeError("Cannot connect to redis://redis:6379//"))

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 503
        assert _handoff_dirs(temp_storage) == []

    def test_a_timed_out_request_leaves_the_image_for_the_still_running_task(
        self, app, db, users, install_dispatch, temp_storage, monkeypatch
    ):
        """
        The 504 is a handover, not an abort: the task keeps running and is
        still reading this file. Deleting it here would break the one path the
        whole synchronous design depends on.
        """
        monkeypatch.setattr(image_routes.settings, "vision_request_timeout_seconds", 0)
        install_dispatch(result=None, ready=False)

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 504
        job_id = response.detail["job_id"]
        assert _handoff_dirs(temp_storage) == [job_id]
        assert (temp_storage / "images" / job_id / "image.png").read_bytes() == PNG_BYTES

    def test_one_requests_cleanup_cannot_touch_another(
        self, app, db, users, eager_vision, temp_storage
    ):
        """
        A directory per job id - a fresh uuid4 per request - is what makes
        deleting a whole directory safe under concurrency. Plant a neighbour and
        watch it survive a completed request.
        """
        neighbour = temp_storage / "images" / "another-in-flight-job"
        neighbour.mkdir(parents=True)
        (neighbour / "image.png").write_bytes(PNG_BYTES)

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 200, response.body
        assert _handoff_dirs(temp_storage) == ["another-in-flight-job"]
        assert (neighbour / "image.png").read_bytes() == PNG_BYTES


class TestTheOrphanSweep:
    """
    The backstop for the one case the task's `finally` cannot cover: the worker
    process being killed outright (hard time limit, OOM), or a message that was
    dispatched and never delivered.

    It is a backstop and nothing more - it runs daily, and a caller in a loop
    fills the disk in minutes. What it must get right is not being eager: an
    inference legitimately holds its image for up to
    `vision_task_timeout_seconds`, so a sweep with a short horizon would delete
    files out from under running work.
    """

    def test_it_removes_a_directory_nobody_came_back_for(self, tmp_path):
        import os

        from workers.vision.image_input import sweep_image_handoffs

        orphan = tmp_path / "images" / "job-that-died"
        orphan.mkdir(parents=True)
        (orphan / "image.png").write_bytes(PNG_BYTES)
        old = time.time() - 7200
        os.utime(orphan, (old, old))

        assert sweep_image_handoffs(tmp_path, max_age_seconds=3600) == 1
        assert not orphan.exists()

    def test_it_leaves_a_directory_a_running_task_may_still_need(self, tmp_path):
        from workers.vision.image_input import sweep_image_handoffs

        fresh = tmp_path / "images" / "job-in-progress"
        fresh.mkdir(parents=True)
        (fresh / "image.png").write_bytes(PNG_BYTES)

        assert sweep_image_handoffs(tmp_path, max_age_seconds=3600) == 0
        assert (fresh / "image.png").exists()

    def test_its_horizon_is_far_longer_than_a_task_can_hold_an_image(self):
        """The monitoring wiring must never sweep inside a legitimate hold."""
        from shared.config import get_settings
        from workers.monitoring import VISION_IMAGE_ORPHAN_MIN_AGE_SECONDS

        assert VISION_IMAGE_ORPHAN_MIN_AGE_SECONDS > (
            get_settings().vision_task_timeout_seconds * 4
        )

    def test_the_daily_cleanup_actually_runs_it(self, tmp_path, monkeypatch):
        """
        A backstop nobody calls is not a backstop. This drives the real
        `cleanup_old_jobs` body, with only its database query stubbed out.
        """
        import os

        import workers.monitoring as monitoring

        monkeypatch.setattr(monitoring.settings, "temp_storage_path", str(tmp_path))
        monkeypatch.setattr(monitoring.settings, "monitoring_enabled", True)
        monkeypatch.setattr(monitoring, "get_old_completed_jobs", lambda **kw: [])
        monkeypatch.setattr(monitoring, "get_redis_client", lambda: None)

        orphan = tmp_path / "images" / "job-whose-worker-was-killed"
        orphan.mkdir(parents=True)
        (orphan / "image.png").write_bytes(PNG_BYTES)
        old = time.time() - 86400
        os.utime(orphan, (old, old))

        assert monitoring.cleanup_old_jobs()["vision_images_swept"] == 1
        assert not orphan.exists()

    def test_a_missing_directory_is_not_an_error(self, tmp_path):
        from workers.vision.image_input import sweep_image_handoffs

        assert sweep_image_handoffs(tmp_path / "nothing-here", max_age_seconds=1) == 0

    def test_a_forged_job_id_cannot_aim_the_deletion(self, tmp_path):
        """
        The path is rebuilt from the job id rather than taken from the message,
        so a hand-crafted broker message cannot turn cleanup into `rm -rf`.
        """
        from workers.vision.image_input import discard_image_handoff, image_handoff_dir

        victim = tmp_path / "important"
        victim.mkdir()
        (victim / "keep.txt").write_text("do not delete me")

        assert discard_image_handoff(tmp_path, "../important") is False
        assert (victim / "keep.txt").exists()

        with pytest.raises(ValueError):
            image_handoff_dir(tmp_path, "../important")


# ---------------------------------------------------------------------------
# Payload validation - all of it before a worker is involved
# ---------------------------------------------------------------------------

class TestPayloadValidation:
    def test_malformed_base64_is_422(self, app, db, users, dispatch):
        response = _post_json(
            app, "/images/describe", {"image_base64": "not base64 at all!!"}, user=users
        )

        assert response.status_code == 422
        assert response.detail["error_code"] == "INVALID_BASE64"
        assert dispatch.calls == []
        assert db.query(Job).count() == 0

    def test_base64_of_something_that_is_not_an_image_is_422(self, app, db, users, dispatch):
        """Valid base64, valid JSON, and not an image: the model never sees it."""
        payload = base64.b64encode(b"#!/bin/sh\nrm -rf /\n").decode()

        response = _post_json(app, "/images/describe", {"image_base64": payload}, user=users)

        assert response.status_code == 422
        assert response.detail["error_code"] == "UNSUPPORTED_IMAGE_FORMAT"
        assert dispatch.calls == []
        assert db.query(Job).count() == 0

    def test_a_lying_content_type_does_not_get_a_pass(self, app, db, users, dispatch):
        """The multipart content-type is caller-supplied; only bytes decide."""
        response = _post_multipart(
            app,
            "/images/describe/upload",
            file_field=("file", "evil.png", b"MZ\x90\x00 not a png", "image/png"),
            user=users,
        )

        assert response.status_code == 422
        assert response.detail["error_code"] == "UNSUPPORTED_IMAGE_FORMAT"
        assert dispatch.calls == []

    def test_an_oversized_image_is_413(self, app, db, users, dispatch, monkeypatch):
        """
        Against the image limit, not `max_file_size_mb` (50MB): the cost here
        is inference, not disk.
        """
        monkeypatch.setattr(image_routes.settings, "vision_max_image_size_mb", 1)
        oversized = base64.b64encode(PNG_BYTES + b"\x00" * (2 * 1024 * 1024)).decode()

        response = _post_json(app, "/images/describe", {"image_base64": oversized}, user=users)

        assert response.status_code == 413
        assert response.detail["error_code"] == "IMAGE_TOO_LARGE"
        assert dispatch.calls == []
        assert db.query(Job).count() == 0

    def test_the_size_limit_is_the_decoded_length(self, app, db, users, dispatch, monkeypatch):
        """
        Base64 inflates by 4/3. Measuring the encoded string would reject
        images ~25% below the documented limit - and, worse, let a caller
        near the limit through by other encodings.
        """
        monkeypatch.setattr(image_routes.settings, "vision_max_image_size_mb", 1)
        # 0.9MB decoded is 1.2MB encoded: over the limit only if measured wrong.
        just_under = base64.b64encode(PNG_BYTES + b"\x00" * (900 * 1024)).decode()

        response = _post_json(app, "/images/describe", {"image_base64": just_under}, user=users)

        assert response.status_code == 200

    def test_an_oversized_multipart_upload_is_413(self, app, db, users, dispatch, monkeypatch):
        monkeypatch.setattr(image_routes.settings, "vision_max_image_size_mb", 1)

        response = _post_multipart(
            app,
            "/images/describe/upload",
            file_field=("file", "big.png", PNG_BYTES + b"\x00" * (2 * 1024 * 1024), "image/png"),
            user=users,
        )

        assert response.status_code == 413
        assert response.detail["error_code"] == "IMAGE_TOO_LARGE"
        assert dispatch.calls == []

    @pytest.mark.parametrize(
        "magic,mime",
        [
            (b"\x89PNG\r\n\x1a\n", "image/png"),
            (b"\xff\xd8\xff\xe0", "image/jpeg"),
            (b"GIF89a", "image/gif"),
            (b"BM", "image/bmp"),
            (b"II*\x00", "image/tiff"),
            (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
        ],
    )
    def test_every_documented_format_is_accepted(self, app, db, users, dispatch, magic, mime):
        payload = base64.b64encode(magic + b"\x00" * 64).decode()

        response = _post_json(app, "/images/describe", {"image_base64": payload}, user=users)

        assert response.status_code == 200
        assert response.json()["image_mime_type"] == mime


# ---------------------------------------------------------------------------
# Unavailability: 503s with a message that says what to do
# ---------------------------------------------------------------------------

class TestVisionUnavailable:
    @pytest.mark.parametrize(
        "path,payload",
        [
            ("/images/describe", {"image_base64": PNG_B64}),
            ("/images/ocr", {"image_base64": PNG_B64}),
        ],
    )
    def test_the_feature_flag_is_checked_first(self, app, db, users, dispatch, monkeypatch, path, payload):
        """
        One flag covers both endpoints - they are one model behind one loader.
        Checked before the body is decoded: the garbage base64 below would be a
        422 if the order were the other way round.
        """
        monkeypatch.setattr(image_routes.settings, "enable_image_description", False)

        response = _post_json(app, path, {**payload, "image_base64": "!!!"}, user=users)

        assert response.status_code == 503
        assert response.detail["error_code"] == "VISION_DISABLED"
        assert "ENABLE_IMAGE_DESCRIPTION=true" in response.detail["message"]
        assert dispatch.calls == []
        assert db.query(Job).count() == 0

    def test_capabilities_is_503_when_disabled(self, app, users, monkeypatch):
        monkeypatch.setattr(image_routes.settings, "enable_image_description", False)

        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.status_code == 503
        assert response.detail["error_code"] == "VISION_DISABLED"

    @pytest.mark.parametrize(
        "error_code,message",
        [
            (
                "VISION_DEPENDENCIES_MISSING",
                "Florence-2 support is not installed. Install the vision extra: "
                "pip install -r backend/requirements-vision.txt",
            ),
            (
                "VISION_MODEL_NOT_DOWNLOADED",
                "Model florence-community/Florence-2-base-ft@0b03b6f1 is not in the "
                "cache and VISION_ALLOW_MODEL_DOWNLOAD=false. Prefetch it with: "
                "make vision-download",
            ),
            ("VISION_MODEL_LOAD_FAILED", "Could not load the model."),
            ("VISION_DEVICE_UNAVAILABLE", "DEVICE=cuda was requested but torch reports no CUDA."),
        ],
    )
    def test_a_structured_task_failure_becomes_the_status_the_caller_sees(
        self, app, db, users, install_dispatch, error_code, message
    ):
        """
        The tasks *return* their failure instead of raising, because an
        exception does not survive the Celery JSON result serializer with its
        code intact. The API's job is to relay it faithfully - the actionable
        message the worker wrote has to reach the caller, not a stack trace.
        """
        install_dispatch(
            result={"ok": False, "error_code": error_code, "http_status": 503, "detail": message}
        )

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 503
        assert response.detail["error_code"] == error_code
        assert response.detail["message"] == message
        assert response.detail["job_id"] == db.query(Job).one().id

    # The decompression-bomb rejection used to be "covered" here by injecting a
    # canned {"error_code": "IMAGE_TOO_LARGE", "http_status": 422} dict - which
    # is the relay above, parametrized once more, and which never touched the
    # guard. Deleting the guard outright left it green. The real thing is now
    # exercised against real PIL in `test_vision_image_guard.py`.

    def test_missing_celery_tasks_are_a_503_not_a_500(self, app, db, users, install_dispatch):
        """The API image does not carry the worker's dependencies by design."""
        install_dispatch(raises=ImportError("No module named 'workers.vision_tasks'"))

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 503
        assert response.detail["error_code"] == "CELERY_UNAVAILABLE"
        assert "worker" in response.detail["message"].lower()

    def test_a_dead_broker_is_a_503_not_a_500(self, app, db, users, install_dispatch):
        install_dispatch(raises=RuntimeError("Cannot connect to redis://redis:6379//"))

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 503
        assert response.detail["error_code"] == "CELERY_UNAVAILABLE"

    def test_an_unexpected_task_crash_is_a_500_without_a_stack_trace(
        self, app, db, users, install_dispatch
    ):
        """`AsyncResult.result` of a task that raised is the exception itself."""
        install_dispatch(result=ValueError("something exploded in the worker"))

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 500
        assert response.detail["error_code"] == "VISION_INFERENCE_FAILED"
        assert "something exploded" not in response.detail["message"]
        assert response.detail["job_id"] == db.query(Job).one().id


# ---------------------------------------------------------------------------
# The timeout is a handover, not a loss
# ---------------------------------------------------------------------------

class TestRequestTimeout:
    def test_a_slow_inference_hands_the_caller_the_job(
        self, app, db, users, install_dispatch, monkeypatch
    ):
        """
        `vision_task_timeout_seconds` is double the request budget on purpose:
        the task outlives the request, so the 504 must point at the job rather
        than pretend the work is gone. This is the whole reason the job is
        created before dispatch.
        """
        monkeypatch.setattr(image_routes.settings, "vision_request_timeout_seconds", 0)
        install_dispatch(result=None, ready=False)

        response = _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert response.status_code == 504
        detail = response.detail
        job_id = db.query(Job).one().id
        assert detail["error_code"] == "VISION_TIMEOUT"
        assert detail["job_id"] == job_id
        assert detail["poll_url"] == f"/jobs/{job_id}"
        assert detail["result_url"] == f"/jobs/{job_id}/result"

    def test_the_task_is_not_revoked_on_timeout(
        self, app, db, users, install_dispatch, monkeypatch, no_redis
    ):
        """Revoking would guarantee the work is lost; the fallback needs it alive."""
        monkeypatch.setattr(image_routes.settings, "vision_request_timeout_seconds", 0)
        fake = install_dispatch(result=None, ready=False)

        _post_json(app, "/images/describe", {"image_base64": PNG_B64}, user=users)

        assert len(fake.calls) == 1
        job_id = db.query(Job).one().id
        # The job stays queued - a timed-out *request* is not a failed *job*.
        assert no_redis.get_job_status(job_id)["status"] == "queued"


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

HEALTHY_WORKER_REPORT = {
    "enabled": True,
    "provider": "florence2",
    "model_id": "florence-community/Florence-2-base-ft",
    "revision": "0b03b6f15a4a211370fb204aee4e7dd48887ea37",
    "device_requested": "auto",
    "device_resolved": "cuda:0",
    "torch_available": True,
    "cuda_available": True,
    "cuda_device_name": "NVIDIA GeForce RTX 5060 Ti",
    "dependencies_installed": True,
    "model_downloaded": True,
    "model_loaded": True,
    "trust_remote_code": False,
    "reason": None,
}


class NoQueueingAllowed:
    """A `vision_capabilities_task.delay` that fails the test if it is called.

    The old implementation put the ops probe on `settings.vision_queue`: one
    slot, no prefetch, behind an inference of up to 120s. That produced both
    halves of the defect - a probe that reported "no worker" whenever a worker
    was busy, and an unbounded backlog an authenticated caller could grow by
    polling, starving real inference with the diagnostic. Reverting to a
    dispatch trips this.
    """

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError(
            "/images/capabilities must not enqueue anything: the vision queue "
            "has one slot and the probe would sit behind an inference."
        )


@pytest.fixture
def no_queueing(monkeypatch):
    from workers.vision_tasks import vision_capabilities_task

    spy = NoQueueingAllowed()
    monkeypatch.setattr(vision_capabilities_task, "delay", spy)
    monkeypatch.setattr(vision_capabilities_task, "apply_async", spy)
    return spy


class TestCapabilities:
    """
    Four states, four distinguishable answers - and being BUSY is not being
    ABSENT.

    The route reads a heartbeat key instead of queueing a probe, so the state
    of the vision queue is irrelevant to the answer. Every test here installs
    `no_queueing`, which turns any dispatch back into a failure.
    """

    def _publish(self, redis_client, **overrides):
        payload = dict(HEALTHY_WORKER_REPORT, published_at=time.time())
        payload.update(overrides)
        redis_client.set_vision_heartbeat(payload, 45)
        return payload

    def test_a_running_worker_is_reported_from_its_heartbeat(
        self, app, users, no_redis, no_queueing
    ):
        self._publish(no_redis)

        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["device_resolved"] == "cuda:0"
        assert body["cuda_device_name"] == "NVIDIA GeForce RTX 5060 Ti"
        assert body["model_loaded"] is True
        assert body["reason"] is None, "a healthy worker leaves nothing to explain"
        assert no_queueing.calls == 0

    def test_a_busy_worker_is_not_reported_as_an_absent_one(
        self, app, users, no_redis, no_queueing, install_dispatch, monkeypatch
    ):
        """
        THE defect. The vision queue is saturated - an inference is running and
        the single slot is taken - and the answer must still be the truth about
        the worker, because the endpoint never touches that queue.
        """
        monkeypatch.setattr(image_routes.settings, "vision_request_timeout_seconds", 0)
        install_dispatch(result=None, ready=False)  # the slot is occupied
        self._publish(no_redis)

        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.status_code == 200
        body = response.json()
        assert body["dependencies_installed"] is True
        assert body["model_loaded"] is True
        assert body["reason"] is None
        assert no_queueing.calls == 0

    def test_no_worker_at_all_answers_200_and_says_so(
        self, app, users, no_redis, no_queueing
    ):
        """An ops probe must not 5xx when the thing it probes is down."""
        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.status_code == 200
        body = response.json()
        assert body["dependencies_installed"] is False
        assert body["model_loaded"] is False
        assert "no vision worker heartbeat" in body["reason"]

    def test_a_stale_heartbeat_is_not_a_live_worker(
        self, app, users, no_redis, no_queueing
    ):
        """
        The failure mode a heartbeat brings with it: a record outliving the
        process that wrote it. The Redis TTL handles the ordinary case, and the
        age carried inside the payload closes the rest - a key written without
        an expiry, or a clock that let one linger, must not read as healthy.
        """
        self._publish(no_redis, published_at=time.time() - 600)

        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.status_code == 200
        body = response.json()
        assert body["dependencies_installed"] is False
        assert body["model_loaded"] is False
        assert "no vision worker heartbeat" in body["reason"]

    def test_a_heartbeat_without_an_age_is_not_trusted(
        self, app, users, no_redis, no_queueing
    ):
        payload = dict(HEALTHY_WORKER_REPORT)
        payload.pop("published_at", None)
        no_redis.set_vision_heartbeat(payload, 45)

        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.json()["dependencies_installed"] is False

    def test_the_heartbeat_carries_a_ttl(self, no_redis):
        """Without an expiry the key would describe a worker forever."""
        self._publish(no_redis)

        from shared.redis_client import VISION_HEARTBEAT_KEY

        assert 0 < no_redis.client.ttl(VISION_HEARTBEAT_KEY) <= 45

    def test_a_worker_without_the_vision_extra_reports_the_reason(
        self, app, users, no_redis, no_queueing
    ):
        """
        Running-but-uninstalled is its own state: the worker is there, so the
        `reason` is the worker's, not the API's "nobody answered".
        """
        self._publish(
            no_redis,
            dependencies_installed=False,
            model_downloaded=False,
            model_loaded=False,
            torch_available=False,
            cuda_available=False,
            device_resolved="cpu",
            reason="missing dependencies: torch, transformers, Pillow.",
        )

        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.status_code == 200
        body = response.json()
        assert body["dependencies_installed"] is False
        assert body["reason"] == "missing dependencies: torch, transformers, Pillow."
        assert "no vision worker heartbeat" not in body["reason"]

    def test_a_dead_redis_still_answers_200(self, app, users, monkeypatch, no_queueing):
        class DeadRedis:
            def get_vision_heartbeat(self):
                raise RuntimeError("Cannot connect to redis://redis:6379//")

        monkeypatch.setattr(image_routes, "get_redis_client", lambda: DeadRedis())

        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.status_code == 200
        body = response.json()
        assert body["dependencies_installed"] is False
        assert "heartbeat" in body["reason"]

    def test_the_capabilities_task_cannot_pile_up_on_the_queue(self):
        """
        The task stays registered (an unknown name under `task_acks_late` is
        redelivered forever, so deleting it would be worse than keeping it), but
        a straggler from an older API build must not spend the single vision
        slot answering about a moment that has passed.
        """
        from workers.vision_tasks import HEARTBEAT_TTL_SECONDS, vision_capabilities_task

        assert vision_capabilities_task.expires == HEARTBEAT_TTL_SECONDS
        assert vision_capabilities_task.time_limit is not None
        assert vision_capabilities_task.name == "workers.vision_tasks.vision_capabilities_task"


class TestTheHeartbeatAndTheRouteAgree:
    """
    The publisher and the reader are in different processes, and nothing else in
    this file makes them agree: every test above writes the payload by hand.
    Here the REAL publisher writes it, through the real `RedisClient`, and the
    real route reads it - so renaming a key in `capabilities_report()` breaks a
    test instead of silently degrading production to "no worker".
    """

    def test_the_real_publisher_produces_a_report_the_route_can_read(
        self, app, users, no_redis, monkeypatch
    ):
        import shared.redis_client as redis_module
        import workers.vision_tasks as vision_tasks

        monkeypatch.setattr(redis_module, "get_redis_client", lambda: no_redis)

        assert vision_tasks.publish_vision_heartbeat() is True

        response = _request(app, "GET", "/images/capabilities", user=users)

        assert response.status_code == 200
        body = response.json()
        # VISION_PROVIDER=stub in conftest: a real describer, no torch.
        assert body["provider"] == "stub"
        assert body["dependencies_installed"] is True
        assert "no vision worker heartbeat" not in (body["reason"] or "")
        # Every field the response model needs actually arrived.
        for field in VisionCapabilitiesResponse.model_fields:
            assert field in body

    def test_the_publisher_does_not_disturb_the_loaded_model(self, no_redis, monkeypatch):
        """
        It runs on a background thread while inference runs on the main one.
        Building (or rebuilding) the process-wide describer from there would
        race the instance that holds the weights, so the probe only ever peeks.
        """
        import shared.redis_client as redis_module
        import workers.vision_tasks as vision_tasks
        from workers.vision.factory import (
            get_image_describer,
            peek_image_describer,
            reset_image_describer,
        )

        monkeypatch.setattr(redis_module, "get_redis_client", lambda: no_redis)
        reset_image_describer()
        try:
            assert peek_image_describer() is None
            vision_tasks.publish_vision_heartbeat()
            assert peek_image_describer() is None, "a probe must not populate the cache"

            loaded = get_image_describer()
            vision_tasks.publish_vision_heartbeat()
            assert peek_image_describer() is loaded, "nor replace it"
        finally:
            reset_image_describer()

    def test_only_a_worker_serving_the_vision_queue_publishes(self, monkeypatch):
        """
        `workers/celery_app.py` imports the vision tasks in EVERY process - the
        API, beat, and the five general workers. If any of those published, the
        endpoint would report a healthy subsystem while `/images/describe` timed
        out against a queue with no consumer: the same lie, from the other side.

        The answer comes from Celery's own `-Q` selection, exercised here on the
        real `Queues` object rather than described by a mock.
        """
        import workers.vision_tasks as vision_tasks
        from shared.config import get_settings
        from workers.celery_app import celery_app

        queues = celery_app.amqp.queues
        previous = queues._consume_from
        try:
            queues.select([get_settings().celery_task_default_queue])
            assert vision_tasks.consumes_vision_queue() is False
            assert vision_tasks.start_vision_heartbeat() is None

            queues.select([get_settings().vision_queue])
            assert vision_tasks.consumes_vision_queue() is True
        finally:
            queues._consume_from = previous

    def test_the_heartbeat_thread_keeps_publishing_while_the_worker_is_busy(
        self, no_redis, monkeypatch
    ):
        """
        The refresh must not be a Celery task: on a one-slot queue it would stop
        being published for exactly as long as the worker was busy - the state
        the heartbeat most needs to describe. A daemon thread does not queue.
        """
        import shared.redis_client as redis_module
        import workers.vision_tasks as vision_tasks
        from shared.config import get_settings
        from workers.celery_app import celery_app

        monkeypatch.setattr(redis_module, "get_redis_client", lambda: no_redis)

        published = []
        monkeypatch.setattr(
            vision_tasks,
            "publish_vision_heartbeat",
            lambda: published.append(time.time()) or True,
        )

        queues = celery_app.amqp.queues
        previous = queues._consume_from
        started = None
        try:
            queues.select([get_settings().vision_queue])
            started = vision_tasks.start_vision_heartbeat(interval=0.01)
            assert started is not None
            thread, stop_event = started
            assert thread.daemon, "shutdown must not wait on a status write"

            deadline = time.time() + 2
            while len(published) < 3 and time.time() < deadline:
                time.sleep(0.01)
        finally:
            if started is not None:
                started[1].set()
                started[0].join(timeout=2)
            queues._consume_from = previous

        # One synchronous publish at start (so a request arriving immediately
        # after boot does not read an empty key), then the loop.
        assert len(published) >= 3
