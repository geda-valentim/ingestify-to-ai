"""
Completion webhook of a MAIN job (`callback_url`; shared/webhooks.py,
workers/webhook_tasks.py, docs/features/webhooks.md).

- `callback_url` is validated before anything is written (422 INVALID_CALLBACK_URL)
  and stored on the job by /upload, /convert and /transcribe;
- one Session listener turns *any* write of a terminal status on a MAIN job into a
  pending delivery, queued after the commit: single document, failed attempts,
  PARTIAL, split PDF (merge), the describe-figures stage, the stuck-job monitor;
  nothing for a retry ahead, a rollback, a child job or a job without a URL;
- nothing in the delivery path can fail the job;
- the delivery is signed, pinned to a public address, follows no redirect and
  retries only what may succeed later.

SQLite with the real models; a local HTTP server stands in for the receiver.
"""
import asyncio
import hashlib
import hmac
import json
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import webhook_routes
from shared import webhooks
from shared.database import get_db
from shared.models import Job, JobStatus, User
from workers import sources, tasks, webhook_tasks
from workers.figure_tasks import STAGE_DESCRIBING

# Shared fixtures and helpers of the purge_source tests (SQLite, fakeredis, fake MinIO)
from tests.test_purge_source import (  # noqa: F401
    ALICE, BOB, JOB_ID, UPLOAD_PATH, Session, _Retry, add_job, api, jwt, run_as_attempt, worker,
)

URL = "https://hooks.example.com/ingestify"


@pytest.fixture
def queued(monkeypatch):
    """The deliveries queued so far: [(job_id, delivery_id)]"""
    calls = []
    monkeypatch.setattr(webhook_tasks.deliver_webhook, "apply_async",
                        lambda args, **kw: calls.append(tuple(args)))
    return calls


def set_job(Session, job_id=JOB_ID, **fields):
    with Session() as db:
        job = db.get(Job, job_id)
        for key, value in fields.items():
            setattr(job, key, value)
        db.commit()


def state_of(Session, job_id=JOB_ID):
    with Session() as db:
        return dict(db.get(Job, job_id).webhook_state or {})


def settle(Session, status, job_id=JOB_ID, **fields):
    fields.setdefault("completed_at", datetime(2026, 10, 1, 9, 0, 0))
    set_job(Session, job_id, status=status, **fields)


# ---------------------------------------------------------------------------
# callback_url validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://hooks.example.com/x",  # http is off by default
    "https://127.0.0.1/x", "https://10.0.0.5/x", "https://[::1]/x", "https://169.254.169.254/latest",
    "https://redis/x", "https://localhost/x", "https://minio.internal/x", "https://printer.local/x",
    "https://user:pw@hooks.example.com/x", "ftp://hooks.example.com/x", "https:///nohost",
    "https://hooks.example.com/" + "a" * 2100, "not a url",
])
def test_unsafe_callback_urls_are_refused(url):
    with pytest.raises(webhooks.InvalidCallbackUrl):
        webhooks.validate_callback_url(url)


def test_a_public_https_url_is_kept_without_its_fragment():
    assert webhooks.validate_callback_url("  https://Hooks.example.com:8443/in?token=1#frag ") == \
        "https://hooks.example.com:8443/in?token=1"


@pytest.mark.parametrize("endpoint", ["/upload", "/convert", "/transcribe"])
def test_invalid_callback_url_is_a_coded_422_before_any_job_exists(api, endpoint):
    data = {"project_id": api.project.id, "callback_url": "https://10.0.0.5/hook"}
    if endpoint == "/convert":
        data["source_type"] = "file"
    r = api.client.post(endpoint, headers=jwt(), data=data,
                        files={"file": ("relatorio.docx", b"PK\x03\x04 doc", "application/octet-stream")})

    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "INVALID_CALLBACK_URL"
    with api.Session() as db:
        assert db.query(Job).count() == 0
    assert api.enqueued == []


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_callback_url_is_stored_on_the_job(api, endpoint):
    data = {"project_id": api.project.id, "callback_url": URL}
    if endpoint == "/convert":
        data["source_type"] = "file"
    r = api.client.post(endpoint, headers=jwt(), data=data,
                        files={"file": ("relatorio.docx", b"PK\x03\x04 doc", "application/octet-stream")})

    assert r.status_code == 200, r.text
    with api.Session() as db:
        job = db.get(Job, r.json()["job_id"])
        assert job.callback_url == URL and job.webhook_state is None
    # Not part of the configuration the dedup fingerprint is made of
    assert "callback_url" not in (api.enqueued[-1].get("options") or {})


def test_url_conversion_and_transcription_store_it_too(api, monkeypatch):
    r = api.client.post("/convert", headers=jwt(), data={
        "project_id": api.project.id, "source_type": "url", "source": "https://example.com/doc.pdf",
        "callback_url": URL})
    assert r.status_code == 200, r.text
    with api.Session() as db:
        assert db.get(Job, r.json()["job_id"]).callback_url == URL

    from api import routes
    monkeypatch.setattr(routes.settings, "enable_audio_transcription", True)
    r = api.client.post("/transcribe", headers=jwt(), data={"project_id": api.project.id, "callback_url": URL},
                        files={"file": ("aula.mp3", b"ID3audio", "audio/mpeg")})
    assert r.status_code == 200, r.text
    with api.Session() as db:
        assert db.get(Job, r.json()["job_id"]).callback_url == URL


# ---------------------------------------------------------------------------
# One event per terminal transition, from the ORM listener
# ---------------------------------------------------------------------------

def add_main(Session, **kw):
    kw.setdefault("status", JobStatus.PROCESSING)
    add_job(Session, **kw)
    set_job(Session, kw.get("job_id", JOB_ID), callback_url=URL)


def test_completed_job_queues_exactly_one_delivery(Session, queued):
    add_main(Session)

    settle(Session, JobStatus.COMPLETED)

    assert len(queued) == 1 and queued[0][0] == JOB_ID
    state = state_of(Session)
    assert state["delivery_id"] == queued[0][1]
    assert (state["event"], state["status"], state["attempts"]) == ("job.completed", "pending", 0)


def test_without_a_callback_url_nothing_is_queued(Session, queued):
    add_job(Session, status=JobStatus.PROCESSING)

    settle(Session, JobStatus.COMPLETED)

    assert queued == [] and state_of(Session) == {}


def test_child_jobs_never_notify(Session, queued):
    for kind in ("SPLIT", "PAGE", "MERGE"):
        add_main(Session, job_id=f"child-{kind}")
        set_job(Session, f"child-{kind}", job_type=kind)
        settle(Session, JobStatus.COMPLETED, f"child-{kind}")
    assert queued == []


@pytest.mark.parametrize("status, event", [
    (JobStatus.FAILED, "job.failed"), (JobStatus.PARTIAL, "job.partial"), (JobStatus.COMPLETED, "job.completed")])
def test_each_terminal_status_has_its_event(Session, queued, status, event):
    add_main(Session)
    settle(Session, status)
    assert state_of(Session)["event"] == event and len(queued) == 1


def test_a_failure_with_a_retry_ahead_waits_as_pending_and_sends_nothing(Session, queued):
    add_main(Session)
    set_job(Session, status=JobStatus.PENDING, error_message="docling exploded")
    settle(Session, JobStatus.PROCESSING)
    assert queued == []


def test_a_rolled_back_terminal_write_sends_nothing(Session, queued):
    add_main(Session)
    with Session() as db:
        job = db.get(Job, JOB_ID)
        job.status = JobStatus.COMPLETED
        db.flush()
        db.rollback()
    with Session() as db:  # and a session closed without a commit
        db.get(Job, JOB_ID).status = JobStatus.FAILED
        db.flush()
    assert queued == [] and state_of(Session) == {}
    # The next real settlement still works (nothing stale was left behind)
    settle(Session, JobStatus.COMPLETED)
    assert len(queued) == 1


def test_writes_that_leave_the_status_alone_do_not_queue_again(Session, queued):
    add_main(Session)
    settle(Session, JobStatus.COMPLETED)
    set_job(Session, char_count=10)
    set_job(Session, status=JobStatus.COMPLETED, error_message=None)
    assert len(queued) == 1


def test_the_delivery_id_is_deterministic_and_a_later_transition_gets_a_new_one(Session, queued):
    add_main(Session)
    settle(Session, JobStatus.PARTIAL)
    first = state_of(Session)["delivery_id"]
    # A redelivered task settles the same way again
    set_job(Session, status=JobStatus.PROCESSING)
    settle(Session, JobStatus.PARTIAL)
    assert state_of(Session)["delivery_id"] == first
    # A page retry later finishes the job
    settle(Session, JobStatus.COMPLETED, completed_at=datetime(2026, 10, 1, 9, 30, 0))
    assert state_of(Session)["delivery_id"] != first
    assert state_of(Session)["event"] == "job.completed"


def test_a_broker_that_raises_never_fails_the_commit(Session, monkeypatch):
    def down(*a, **kw):
        raise ConnectionError("broker down")
    monkeypatch.setattr(webhook_tasks.deliver_webhook, "apply_async", down)
    add_main(Session)

    settle(Session, JobStatus.COMPLETED)

    with Session() as db:
        job = db.get(Job, JOB_ID)
        assert job.status == JobStatus.COMPLETED and job.webhook_state["status"] == "pending"


def test_single_document_conversion_sends_one_event(worker, queued):
    add_main(worker.Session, status=JobStatus.PENDING)

    assert worker.convert()["status"] == "completed"

    assert len(queued) == 1
    assert state_of(worker.Session)["event"] == "job.completed"


def test_a_failing_receiver_or_broker_does_not_touch_the_conversion(worker, monkeypatch):
    def down(*a, **kw):
        raise ConnectionError("broker down")
    monkeypatch.setattr(webhook_tasks.deliver_webhook, "apply_async", down)
    add_main(worker.Session, status=JobStatus.PENDING)

    result = worker.convert()

    assert result["status"] == "completed"
    assert worker.job().status == JobStatus.COMPLETED
    assert worker.converter.convert_to_markdown.call_count == 1  # not retried


def test_last_failed_attempt_sends_job_failed_and_a_retry_ahead_sends_nothing(worker, queued, monkeypatch):
    add_main(worker.Session, status=JobStatus.PENDING)
    worker.converter.convert_to_markdown.side_effect = RuntimeError("docling exploded")

    with pytest.raises(_Retry):
        run_as_attempt(tasks.process_conversion, worker.convert, retries=0, monkeypatch=monkeypatch)
    assert queued == []

    with pytest.raises(_Retry):
        run_as_attempt(tasks.process_conversion, worker.convert,
                       retries=tasks.process_conversion.max_retries, monkeypatch=monkeypatch)
    assert len(queued) == 1
    assert state_of(worker.Session)["event"] == "job.failed"


def test_split_pdf_sends_one_event_after_the_merge_and_none_for_its_children(worker, queued):
    add_main(worker.Session, path=f"uploads/{JOB_ID}/livro.pdf", filename="livro.pdf",
             pages={1: JobStatus.COMPLETED, 2: JobStatus.COMPLETED})
    with worker.Session() as db:
        for number in (1, 2):  # the page jobs settle on their own rows, never MAIN
            db.get(Job, JOB_ID).pages_completed = number
            db.commit()
    assert queued == []

    worker.merge()

    assert len(queued) == 1 and queued[0][0] == JOB_ID
    assert state_of(worker.Session)["event"] == "job.completed"


def test_the_describe_stage_notifies_at_its_completed_commit_not_when_it_begins(Session, queued):
    add_main(Session)
    set_job(Session, figures_stage=STAGE_DESCRIBING)  # begin(): still PROCESSING
    assert queued == []

    settle(Session, JobStatus.COMPLETED, figures_stage="finishing")  # finalize's commit
    assert len(queued) == 1

    set_job(Session, figures_stage=None)  # the post-completion steps
    assert len(queued) == 1


def test_the_stuck_job_monitor_failing_a_job_notifies(Session, queued):
    add_main(Session)
    settle(Session, JobStatus.FAILED, error_message="STUCK: no heartbeat")
    assert len(queued) == 1 and state_of(Session)["event"] == "job.failed"


# ---------------------------------------------------------------------------
# Signature and payload
# ---------------------------------------------------------------------------

def test_signing_secret_is_per_user_stable_and_never_the_jwt_key():
    from shared.config import get_settings

    alice, bob = webhooks.signing_secret(ALICE), webhooks.signing_secret(BOB)
    assert alice != bob and alice == webhooks.signing_secret(ALICE)
    assert alice.startswith("whsec_") and get_settings().jwt_secret_key not in alice


def test_secret_endpoint_answers_each_user_with_their_own_secret(Session):
    app = FastAPI()
    app.include_router(webhook_routes.router)
    with Session() as db:
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        a = client.get("/webhooks/signing-secret", headers=jwt(ALICE))
        b = client.get("/webhooks/signing-secret", headers=jwt(BOB))
    assert a.status_code == b.status_code == 200
    assert a.json()["secret"] == webhooks.signing_secret(ALICE) != b.json()["secret"]
    assert client.get("/webhooks/signing-secret").status_code in (401, 403)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

class Receiver:
    """A local HTTP receiver: records what it got, answers what the test says"""

    def __init__(self):
        self.status, self.location, self.body = 200, None, b"ok"
        self.requests = []
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                size = int(self.headers.get("Content-Length") or 0)
                receiver.requests.append({"path": self.path, "headers": dict(self.headers),
                                          "body": self.rfile.read(size)})
                self.send_response(receiver.status)
                if receiver.location:
                    self.send_header("Location", receiver.location)
                self.send_header("Content-Length", str(len(receiver.body)))
                self.end_headers()
                self.wfile.write(receiver.body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_port

    def close(self):
        self.server.shutdown()


@pytest.fixture
def receiver():
    r = Receiver()
    yield r
    r.close()


@pytest.fixture
def allow_loopback(monkeypatch):
    original = sources._is_public_ip
    monkeypatch.setattr(sources, "_is_public_ip", lambda ip: ip.is_loopback or original(ip))


@pytest.fixture
def resolve_to(monkeypatch):
    def set_addresses(*addresses):
        async def fake_getaddrinfo(self, host, port, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]
        monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)
    return set_addresses


@pytest.fixture
def delivery(Session, queued, monkeypatch, receiver, allow_loopback):
    """A completed MAIN job pointing at the local receiver, and a way to run one attempt"""
    monkeypatch.setattr(webhook_tasks, "SessionLocal", Session)
    add_main(Session)
    set_job(Session, callback_url=f"http://127.0.0.1:{receiver.port}/hook", name="relatorio.docx",
            error_message=None, total_pages=2, pages_completed=2, pages_failed=0)
    settle(Session, JobStatus.COMPLETED)
    delivery_id = state_of(Session)["delivery_id"]
    retries = []

    def attempt(retry_number=0, delivery=delivery_id):
        task = webhook_tasks.deliver_webhook
        monkeypatch.setattr(task, "retry", lambda *a, **kw: retries.append(kw.get("countdown")) or _Retry())
        task.push_request(id="webhook-task", retries=retry_number, called_directly=False)
        try:
            return task.run(JOB_ID, delivery)
        except _Retry:
            return "retry"
        finally:
            task.pop_request()

    return type("D", (), {"attempt": staticmethod(attempt), "id": delivery_id, "retries": retries,
                          "Session": Session, "receiver": receiver})


def test_a_2xx_marks_the_delivery_delivered_with_a_verifiable_signature(delivery):
    assert delivery.attempt() == "delivered"

    (request,) = delivery.receiver.requests
    headers = {k.lower(): v for k, v in request["headers"].items()}
    assert headers["x-ingestify-event"] == "job.completed" and headers["x-ingestify-delivery"] == delivery.id
    assert headers["user-agent"] == "Ingestify-Webhook/1" and headers["content-type"] == "application/json"
    stamp, signature = (part.split("=", 1)[1] for part in headers["x-ingestify-signature"].split(","))
    expected = hmac.new(webhooks.signing_secret(ALICE).encode(), f"{stamp}.".encode() + request["body"],
                        hashlib.sha256).hexdigest()
    assert signature == expected
    body = json.loads(request["body"])
    assert body["id"] == delivery.id and body["event"] == "job.completed"
    assert body["data"]["job_id"] == JOB_ID and body["data"]["result_url"] == f"/jobs/{JOB_ID}/result"
    assert body["data"]["pages_completed"] == 2 and body["data"]["error"] is None
    assert not {"markdown", "result", "content"} & (set(body) | set(body["data"]))
    assert request["body"] == json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()

    state = state_of(delivery.Session)
    assert (state["status"], state["attempts"], state["last_http_status"]) == ("delivered", 1, 200)
    assert state["delivered_at"]
    with delivery.Session() as db:  # the job itself is untouched
        job = db.get(Job, JOB_ID)
        assert job.status == JobStatus.COMPLETED and job.completed_at == datetime(2026, 10, 1, 9, 0, 0)


def test_a_failed_job_carries_its_error_code_and_message(delivery):
    set_job(delivery.Session, status=JobStatus.PROCESSING)
    settle(delivery.Session, JobStatus.FAILED, error_message="DOCUMENT_UNREADABLE: the file is encrypted")
    new_id = state_of(delivery.Session)["delivery_id"]

    assert delivery.attempt(delivery=new_id) == "delivered"

    body = json.loads(delivery.receiver.requests[-1]["body"])
    assert body["event"] == "job.failed"
    assert body["data"]["error"] == {"code": "DOCUMENT_UNREADABLE", "message": "the file is encrypted"}


def test_a_redirect_is_not_followed_and_fails_for_good(delivery):
    delivery.receiver.status, delivery.receiver.location = 302, "http://169.254.169.254/latest/meta-data/"

    assert delivery.attempt() == "failed"

    assert len(delivery.receiver.requests) == 1 and delivery.retries == []
    state = state_of(delivery.Session)
    assert (state["status"], state["last_http_status"], state["last_error"]) == ("failed", 302, "HTTP_302")


def test_a_5xx_is_retried_with_a_growing_delay_until_the_attempts_run_out(delivery):
    delivery.receiver.status = 500

    assert delivery.attempt(0) == "retry"
    assert delivery.retries == [30]
    assert state_of(delivery.Session)["status"] == "pending"
    assert delivery.attempt(1) == "retry" and delivery.retries == [30, 120]
    assert delivery.attempt(4) == "retry" and delivery.retries[-1] == 7200

    assert delivery.attempt(5) == "failed"  # the sixth attempt
    state = state_of(delivery.Session)
    assert (state["status"], state["attempts"], state["last_http_status"]) == ("failed", 6, 500)


@pytest.mark.parametrize("status", [408, 429, 503])
def test_other_retryable_statuses(delivery, status):
    delivery.receiver.status = status
    assert delivery.attempt() == "retry"


@pytest.mark.parametrize("status", [400, 401, 404, 410])
def test_a_4xx_is_final(delivery, status):
    delivery.receiver.status = status
    assert delivery.attempt() == "failed" and delivery.retries == []
    assert state_of(delivery.Session)["last_http_status"] == status


def test_a_connection_error_is_retried(delivery):
    with socket.socket() as closed:  # a port nobody listens on
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    set_job(delivery.Session, callback_url=f"http://127.0.0.1:{port}/hook")
    assert delivery.attempt() == "retry"
    assert state_of(delivery.Session)["last_error"].startswith("NETWORK_ERROR")


def test_a_host_that_resolves_to_a_private_address_is_refused_without_connecting(
        delivery, resolve_to, monkeypatch):
    monkeypatch.undo()  # the real _is_public_ip: loopback is private again
    monkeypatch.setattr(webhook_tasks, "SessionLocal", delivery.Session)
    set_job(delivery.Session, callback_url=f"http://hooks.example.com:{delivery.receiver.port}/hook")
    resolve_to("10.0.0.5")

    assert delivery.attempt() == "failed"

    assert delivery.receiver.requests == [] and delivery.retries == []
    assert state_of(delivery.Session)["last_error"] == "CALLBACK_URL_NOT_PUBLIC"


def test_the_connection_goes_to_the_validated_address_with_the_original_host(delivery, resolve_to):
    set_job(delivery.Session, callback_url=f"http://hooks.example.com:{delivery.receiver.port}/hook?t=1")
    resolve_to("127.0.0.1")

    assert delivery.attempt() == "delivered"

    (request,) = delivery.receiver.requests
    assert request["headers"]["Host"] == f"hooks.example.com:{delivery.receiver.port}"
    assert request["path"] == "/hook?t=1"


def test_a_huge_answer_is_cut_and_still_counts(delivery):
    delivery.receiver.body = b"x" * (200 * 1024)
    assert delivery.attempt() == "delivered"


def test_a_stale_delivery_does_nothing(delivery):
    assert delivery.attempt(delivery="not-the-current-delivery") == "superseded"
    assert delivery.receiver.requests == []
    # And a job that went back to work is not announced as done
    set_job(delivery.Session, status=JobStatus.PROCESSING)
    assert delivery.attempt() == "superseded" and delivery.receiver.requests == []


def test_an_unexpected_error_is_recorded_and_never_raised(delivery, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("bug")
    monkeypatch.setattr(webhooks, "build_payload", boom)

    assert delivery.attempt() == "failed"
    assert state_of(delivery.Session)["last_error"] == "INTERNAL_ERROR: RuntimeError"


# ---------------------------------------------------------------------------
# GET /jobs/{id} and a duplicate upload
# ---------------------------------------------------------------------------

def test_job_status_reports_the_delivery_with_the_host_only(api, queued):
    add_main(api.Session, status=JobStatus.PROCESSING)
    set_job(api.Session, callback_url="https://hooks.example.com/in?token=s3cret")
    settle(api.Session, JobStatus.COMPLETED)
    api.db.expire_all()

    body = api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()

    assert body["webhook"]["url_host"] == "hooks.example.com"
    assert (body["webhook"]["status"], body["webhook"]["attempts"]) == ("pending", 0)
    assert body["webhook"]["delivery_id"] == state_of(api.Session)["delivery_id"]
    assert "s3cret" not in json.dumps(body)


def test_job_without_a_callback_has_no_webhook_block(api):
    add_job(api.Session, status=JobStatus.COMPLETED)
    assert api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()["webhook"] is None


CONTENT = b"PK\x03\x04 dedup document"


def post_duplicate(api, url=URL):
    return api.client.post("/upload", headers=jwt(), data={"project_id": api.project.id, "callback_url": url},
                           files={"file": ("relatorio.docx", CONTENT, "application/octet-stream")})


def test_duplicate_upload_of_a_completed_job_sends_its_event_once(api, queued):
    add_job(api.Session, status=JobStatus.COMPLETED, checksum=hashlib.sha256(CONTENT).hexdigest(),
            project_id=api.project.id)
    set_job(api.Session, completed_at=datetime(2026, 10, 1, 9, 0, 0))

    r = post_duplicate(api)
    assert r.status_code == 200 and r.json()["duplicate"] is True
    assert queued == [(JOB_ID, state_of(api.Session)["delivery_id"])]
    assert state_of(api.Session)["event"] == "job.completed"

    post_duplicate(api)  # the same URL again: nothing new to announce
    assert len(queued) == 1


def test_duplicate_upload_of_a_running_job_notifies_when_it_finishes(api, queued):
    add_job(api.Session, status=JobStatus.PROCESSING, checksum=hashlib.sha256(CONTENT).hexdigest(),
            project_id=api.project.id)

    assert post_duplicate(api).json()["duplicate"] is True
    assert queued == []
    settle(api.Session, JobStatus.COMPLETED)
    assert len(queued) == 1
