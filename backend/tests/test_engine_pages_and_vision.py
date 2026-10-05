"""
Slice 8 of spec 0003: document conversion routed per PDF page and vision placed
synchronously, both on the local engine, plus the S-01 fix that had to come first
(no user JWT, no provider token in Celery messages or backlog payloads).

Zero-config parity: without a document_conversion route the split fans out with
convert_page_task.delay and the page retry with process_page.delay, exactly as
before (tests/test_tasks_page_conversion.py and the contract tests pin those);
without a vision route the API never reserves anything.
"""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api import image_routes, routes
from api.projects_api import LocationFields
from shared.engines import dispatch, ledger
from shared.models import Engine, EngineUsage, FeatureRoute, Job, JobDispatch, JobStatus, Page
from tests._engines_world import ALICE, World
from workers import tasks, vision_tasks
from workers.engines import sweeper

LOCAL = "eng-local"
PARENT = "11111111-2222-4333-8444-555555555555"


@pytest.fixture
def world(monkeypatch, tmp_path):
    w = World(monkeypatch, tmp_path)
    with w.Session() as db:
        local = db.get(Engine, LOCAL)
        local.config = {**local.config, "features": {**local.config["features"],
                                                     "document_conversion": {"workers": 2},
                                                     "vision": {"gpu_ref": "gpu0", "workers": 1}}}
        db.commit()
    yield w
    w.close()


def route(world, feature, *steps, **values):
    raw = []
    for position, step in enumerate(steps, start=1):
        raw.append({"engine_ids": step, "group_strategy": "priority", "position": position})
    with world.Session() as db:
        row = db.get(FeatureRoute, feature) or FeatureRoute(feature=feature, version=0)
        row.steps = raw
        row.state = values.pop("state", "active")
        for k, v in values.items():
            setattr(row, k, v)
        row.version = (row.version or 0) + 1
        db.merge(row)
        db.commit()
    world.dispatcher_alive()
    dispatch.reset_caches()


# --- document_conversion: pages through the backlog --------------------------------------


@pytest.fixture
def pages(world, monkeypatch, tmp_path):
    """A parent job of 3 pages, a fake converter/ES/MinIO, and split_pdf_task ready to run"""
    with world.Session() as db:
        db.add(Job(id=PARENT, user_id=ALICE, filename="doc.pdf", name="doc.pdf", job_type="MAIN",
                   status=JobStatus.PROCESSING, source_type="file"))
        db.commit()
    world.redis.set_job_status(job_id=PARENT, job_type="main", status="processing", progress=20)
    page_dir = tmp_path / PARENT / "pages"
    page_dir.mkdir(parents=True)
    page_files = []
    for n in (1, 2, 3):
        path = page_dir / f"page_{n:04d}.pdf"
        path.write_bytes(b"%PDF-1.4 page")
        page_files.append((n, path, f"pages/{PARENT}/page_{n:04d}.pdf"))
    splitter = MagicMock(name="PDFSplitter")
    splitter.return_value.split_pdf.return_value = page_files
    monkeypatch.setattr(tasks, "PDFSplitter", splitter)

    state = SimpleNamespace(fail=None, converted=[], merges=[], delayed=[])

    class Converter:
        def convert_to_markdown(self, path, options=None):
            if state.fail:
                raise state.fail
            state.converted.append(path)
            return {"markdown": f"# {path.name}", "metadata": {"words": 1, "pages": 1}}

    es = MagicMock(name="es")
    es.store_page_result.return_value = True
    minio = MagicMock(name="minio")
    monkeypatch.setattr(tasks, "get_converter", lambda *a, **k: Converter())
    monkeypatch.setattr(tasks, "get_es_client", lambda: es)
    monkeypatch.setattr(tasks, "get_minio_client", lambda: minio)
    monkeypatch.setattr(tasks.merge_pages_task, "delay", lambda **kw: state.merges.append(kw))
    monkeypatch.setattr(tasks.convert_page_task, "delay", lambda **kw: state.delayed.append(kw))
    return state


def split(world):
    tasks.split_pdf_task.push_request(retries=0)
    try:
        return tasks.split_pdf_task.run(split_job_id="split-1", parent_job_id=PARENT,
                                        file_path=str(world.tmp / "doc.pdf"),
                                        options={"docling_preset": "fast", "auth_token": "eyJ-should-not-travel"})
    finally:
        tasks.split_pdf_task.pop_request()


def page_runs(world):
    return [s for s in world.celery.named(dispatch.CONVERT_PAGE) if "usage_id" in s.kwargs]


def run_page(kwargs):
    tasks.convert_page_task.push_request(retries=0)
    try:
        return tasks.convert_page_task.run(**kwargs)
    finally:
        tasks.convert_page_task.pop_request()


def test_without_a_route_the_split_fans_out_exactly_as_today(world, pages):
    split(world)
    assert [d["page_number"] for d in pages.delayed] == [1, 2, 3]
    assert "usage_id" not in pages.delayed[0]
    assert world.count(JobDispatch) == 0 and world.count(EngineUsage) == 0 and world.celery.sent == []


def test_with_a_route_each_page_joins_the_backlog_without_a_probe(world, pages):
    route(world, "document_conversion", [LOCAL])
    split(world)

    assert pages.delayed == []  # nothing on today's path
    assert len(world.redis.get_page_jobs(PARENT)) == 3
    with world.Session() as db:
        rows = db.query(JobDispatch).order_by(JobDispatch.id).all()
        assert [(d.feature, d.subject_type, d.state, d.job_id) for d in rows] == \
            [("document_conversion", "page", "waiting", PARENT)] * 3
        kwargs = rows[0].payload["kwargs"]
        assert kwargs["page_number"] == 1 and kwargs["parent_job_id"] == PARENT
        assert kwargs["options"] == {"docling_preset": "fast"}  # allowlisted: no token rides along
        assert "eyJ" not in str(rows[0].payload)
    assert world.celery.named(dispatch.PROBE_TASK) == []


def test_with_the_dispatcher_down_pages_go_straight_to_the_local_workers(world, pages):
    route(world, "document_conversion", [LOCAL])
    world.dispatcher_alive(at=world.now - timedelta(hours=1))
    split(world)
    runs = page_runs(world)
    assert len(runs) == 3 and all(r.queue == "ingestify" for r in runs)  # fallback rows count in flight
    assert world.count(JobDispatch, state="bypassed") == 3
    assert run_page(runs[0].kwargs)["status"] == "completed"


def test_pages_are_placed_up_to_the_local_capacity_and_run_with_their_reservation(world, pages):
    route(world, "document_conversion", [LOCAL])
    split(world)
    result = world.tick()
    assert len(result.placed) == 2  # document_conversion workers=2
    first, second = page_runs(world)
    assert first.queue == "ingestify" and first.kwargs["usage_id"]

    assert run_page(first.kwargs)["status"] == "completed"
    usage = world.usage(first.kwargs["usage_id"])
    assert usage.status == "settled" and usage.outcome == "succeeded" and usage.subject_type == "page"
    with world.Session() as db:
        page = db.query(Page).filter(Page.job_id == PARENT, Page.page_number == 1).one()
        assert page.status == JobStatus.COMPLETED
        assert db.query(JobDispatch).filter(JobDispatch.subject_id == first.kwargs["page_job_id"]).one().state == "done"
    assert world.job(PARENT).pages_completed == 1

    # The slot freed: the third page goes out on the next tick; the last page triggers the merge
    world.tick()
    third = page_runs(world)[2]
    run_page(second.kwargs)
    assert pages.merges == []
    run_page(third.kwargs)
    assert len(pages.merges) == 1
    assert world.job(PARENT).status == JobStatus.PROCESSING  # the merge completes it, as today


def test_a_redelivered_page_message_is_acknowledged_without_running(world, pages):
    route(world, "document_conversion", [LOCAL])
    split(world)
    world.tick()
    first = page_runs(world)[0]
    run_page(first.kwargs)
    converted = len(pages.converted)
    assert run_page(first.kwargs)["status"] == ledger.LOST
    assert len(pages.converted) == converted


def test_a_failed_page_goes_back_to_the_backlog_and_never_fails_the_document(world, pages):
    route(world, "document_conversion", [LOCAL], max_attempts=2)
    split(world)
    world.tick()
    first = page_runs(world)[0]
    pages.fail = RuntimeError("docling exploded")

    assert run_page(first.kwargs)["status"] == "queued"  # no task.retry: the backlog decides
    with world.Session() as db:
        d = db.query(JobDispatch).filter(JobDispatch.subject_id == first.kwargs["page_job_id"]).one()
        assert d.state == "waiting" and d.job_failures == 1 and d.not_before is not None and d.priority == 0
        page = db.query(Page).filter(Page.job_id == PARENT, Page.page_number == 1).one()
        assert page.status == JobStatus.PENDING
    assert world.redis.get_job_status(first.kwargs["page_job_id"])["status"] == "queued"
    assert world.job(PARENT).status == JobStatus.PROCESSING

    # Second counted failure: the page - only the page - fails for good
    world.tick(at=world.now + timedelta(minutes=5))
    retry = [r for r in page_runs(world) if r.kwargs["page_number"] == 1][-1]
    assert run_page(retry.kwargs)["status"] == "failed"
    with world.Session() as db:
        page = db.query(Page).filter(Page.job_id == PARENT, Page.page_number == 1).one()
        assert page.status == JobStatus.FAILED and "docling exploded" in page.error_message
    parent = world.job(PARENT)
    assert parent.status == JobStatus.PROCESSING and parent.pages_failed == 1
    status = world.redis.get_job_status(retry.kwargs["page_job_id"])
    assert status["status"] == "failed" and status["type"] == "page"


def test_a_routed_page_of_a_deleted_job_is_cancelled_at_its_claim(world, pages):
    route(world, "document_conversion", [LOCAL])
    split(world)
    world.tick()
    first = page_runs(world)[0]
    with world.Session() as db:
        db.query(Page).filter(Page.job_id == PARENT).delete()
        db.delete(db.get(Job, PARENT))
        db.commit()
    assert run_page(first.kwargs)["status"] == ledger.CANCELLED
    assert pages.converted == []


def test_the_page_retry_endpoint_goes_through_the_route(world, monkeypatch, tmp_path):
    route(world, "document_conversion", [LOCAL])
    monkeypatch.setattr(routes, "SessionLocal", world.Session)
    monkeypatch.setattr(routes, "get_redis_client", lambda: world.redis)
    monkeypatch.setattr(routes, "_engine_celery", lambda: world.celery)
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(routes.get_settings(), "temp_storage_path", str(tmp_path))
    delayed = []
    monkeypatch.setattr(tasks.process_page, "delay", lambda **kw: delayed.append(kw))
    with world.Session() as db:
        db.add(Job(id=PARENT, user_id=ALICE, filename="doc.pdf", job_type="MAIN", status=JobStatus.PROCESSING))
        db.add(Page(id="p7", job_id=PARENT, page_number=7, page_job_id="old", status=JobStatus.FAILED))
        db.commit()
    (tmp_path / "uploads" / PARENT).mkdir(parents=True)
    (tmp_path / "uploads" / PARENT / "doc.pdf").write_bytes(b"%PDF-1.4")

    db = world.Session()
    try:
        alice = db.get(routes.User, ALICE)
        body = asyncio.run(routes.retry_failed_page(PARENT, 7, current_user=alice, owned_job=db.get(Job, PARENT),
                                                    db_page=db.get(Page, "p7"), db=db))
    finally:
        db.close()

    assert delayed == []
    with world.Session() as s:
        d = s.query(JobDispatch).one()
        assert d.subject_type == "page" and d.subject_id == body["new_page_job_id"] and d.state == "waiting"
        assert d.payload["kwargs"]["source_pdf_path"].endswith("doc.pdf")
        assert d.payload["kwargs"]["page_number"] == 7


def test_stuck_detection_ignores_a_job_whose_pages_wait_in_the_backlog(world, pages, monkeypatch):
    import shared.queries as queries

    route(world, "document_conversion", [LOCAL])
    split(world)
    with world.Session() as db:
        db.get(Job, PARENT).started_at = world.now - timedelta(hours=2)
        db.commit()
    assert PARENT not in {j.id for j in queries.get_stuck_jobs(threshold_minutes=30)}


# --- vision: placed inline, no backlog ---------------------------------------------------


def place(world, job_id="vision-job-1", user=ALICE, is_admin=False):
    return dispatch.place_now(feature="vision", subject_id=job_id, job_id=job_id, user_id=user,
                              is_admin=is_admin, session_factory=world.Session, now=world.now)


def test_without_a_vision_route_nothing_is_reserved(world):
    assert place(world).outcome == "today"
    assert world.count(EngineUsage) == 0


def test_a_vision_route_reserves_a_local_slot_and_falls_back_to_the_queue_when_full(world):
    route(world, "vision", [LOCAL])
    first = place(world, "v-1")
    assert first.outcome == "placed" and first.engine_slug == "local"
    usage = world.usage(first.usage_id)
    assert (usage.subject_type, usage.feature, usage.status) == ("vision_request", "vision", "reserved")
    assert world.count(JobDispatch) == 0  # no backlog for a synchronous feature

    second = place(world, "v-2")  # vision workers=1: full -> today's queue, never refused
    assert second.outcome == "today" and "full" in second.reason


def test_a_vision_route_without_a_local_step_answers_unavailable(world):
    world.add_remote("fake_v", config={"features": {"vision": {"gpu_type": "L4", "workers": 1}}})
    route(world, "vision", ["eng-fake_v"])
    placement = place(world, is_admin=True)
    assert placement.outcome == "unavailable" and placement.retry_after == dispatch.SYNC_RETRY_AFTER_SECONDS
    assert world.count(EngineUsage) == 0


PNG = __import__("base64").b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def vision_api(world, monkeypatch, tmp_path):
    monkeypatch.setattr(image_routes, "SessionLocal", world.Session)
    monkeypatch.setattr(image_routes, "get_redis_client", lambda: world.redis)
    monkeypatch.setattr(image_routes.settings, "temp_storage_path", str(tmp_path))
    sent = []

    class Result:
        def ready(self):
            return True

        result = {"ok": True, "description": "d", "width": 1, "height": 1, "model": {}}

    def dispatch_task(kind, **kwargs):
        sent.append(kwargs)
        return Result()

    monkeypatch.setattr(image_routes, "_dispatch_vision_task", dispatch_task)
    return sent


def run_vision(world):
    db = world.Session()
    try:
        alice = db.get(routes.User, ALICE)
        return asyncio.run(image_routes._run_vision("describe", PNG, "x.png", None, alice, db))
    finally:
        db.close()


def test_the_vision_api_hands_its_reservation_to_the_worker(world, vision_api):
    route(world, "vision", [LOCAL])
    run_vision(world)
    [kwargs] = vision_api
    usage = world.usage(kwargs["usage_id"])
    assert usage.status == "reserved" and usage.published_at is not None


def test_the_vision_api_without_a_route_sends_no_usage_id(world, vision_api):
    run_vision(world)
    assert "usage_id" not in vision_api[0] and world.count(EngineUsage) == 0


def test_the_vision_api_answers_503_with_retry_after_when_nothing_can_take_it(world, vision_api):
    world.add_remote("fake_v", config={"features": {"vision": {"gpu_type": "L4", "workers": 1}}})
    route(world, "vision", ["eng-fake_v"])
    with pytest.raises(HTTPException) as exc:
        run_vision(world)
    assert exc.value.status_code == 503 and exc.value.headers["Retry-After"] == "30"
    assert exc.value.detail["error_code"] == "VISION_ENGINE_UNAVAILABLE"
    assert vision_api == []


def test_the_vision_worker_claims_and_settles_its_reservation(world, monkeypatch):
    route(world, "vision", [LOCAL])
    placement = place(world, "v-9")
    payload = {"ok": True, "description": "x", "width": 1, "height": 1}
    monkeypatch.setattr(vision_tasks, "_run_inner", lambda *a: payload)
    monkeypatch.setattr(vision_tasks, "_set_status", lambda *a, **k: None)
    monkeypatch.setattr(vision_tasks, "discard_image_handoff", lambda *a: None)

    assert vision_tasks._run("describe", "v-9", "/tmp/x.png", None, usage_id=placement.usage_id) == payload
    usage = world.usage(placement.usage_id)
    assert usage.status == "settled" and usage.outcome == "succeeded"

    # A redelivery (or a lapsed reservation) still answers - outside the accounting
    assert vision_tasks._run("describe", "v-9", "/tmp/x.png", None, usage_id=placement.usage_id) == payload


def test_the_vision_worker_settles_a_typed_failure(world, monkeypatch):
    route(world, "vision", [LOCAL])
    placement = place(world, "v-10")
    failure = {"ok": False, "error_code": "VISION_MODEL_MISSING", "http_status": 503, "detail": "no weights"}
    monkeypatch.setattr(vision_tasks, "_run_inner", lambda *a: failure)
    monkeypatch.setattr(vision_tasks, "_set_status", lambda *a, **k: None)
    monkeypatch.setattr(vision_tasks, "discard_image_handoff", lambda *a: None)
    assert vision_tasks._run("ocr", "v-10", "/tmp/x.png", None, usage_id=placement.usage_id) == failure
    usage = world.usage(placement.usage_id)
    assert usage.status == "settled" and usage.outcome == "failed" and usage.error_code == "VISION_MODEL_MISSING"


def test_the_sweeper_gives_back_a_vision_slot_that_was_never_sent(world):
    route(world, "vision", [LOCAL])
    placement = place(world, "v-11")
    counts = sweeper.sweep(celery=world.celery, session_factory=world.Session, now=world.now + timedelta(seconds=90),
                           redis_client=world.redis)
    assert counts["released"] == 1 and world.usage(placement.usage_id).status == "released"
    assert world.celery.named("workers.vision_tasks.describe_image_task") == []


# --- S-01: no user JWT, no provider token in Celery messages ------------------------------


@pytest.fixture
def convert(world, monkeypatch, tmp_path):
    enqueued = []
    monkeypatch.setattr(routes, "get_redis_client", lambda: world.redis)
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(tasks.process_conversion, "delay", lambda **kw: enqueued.append(kw))

    def call(source_type, source, **headers):
        db = world.Session()
        try:
            alice = db.get(routes.User, ALICE)
            return asyncio.run(routes.convert_document(
                source_type=source_type, source=source, file=None, name=None, tags=None,
                authorization=headers.get("authorization"), source_token=headers.get("source_token"),
                location=LocationFields(project="Engines"), current_user=alice, db=db))
        finally:
            db.close()

    call.enqueued = enqueued
    return call


def test_the_ingestify_jwt_never_reaches_the_task(convert):
    convert("url", "https://example.com/a.pdf", authorization="Bearer eyJ.user.jwt")
    [kwargs] = convert.enqueued
    assert "auth_token" not in kwargs and "eyJ" not in str(kwargs)


def test_a_cloud_source_needs_its_own_token_header(convert):
    with pytest.raises(HTTPException) as exc:
        convert("gdrive", "file-id", authorization="Bearer eyJ.user.jwt")
    assert exc.value.status_code == 400 and "X-Source-Token" in exc.value.detail
    assert convert.enqueued == []


def test_the_provider_token_goes_out_of_band_and_is_dropped_after_the_download(world, convert, monkeypatch):
    response = convert("dropbox", "/docs/a.pdf", authorization="Bearer eyJ.user.jwt", source_token="sl.provider")
    [kwargs] = convert.enqueued
    job_id = str(response.job_id)
    assert "auth_token" not in kwargs and "sl.provider" not in str(kwargs) and "eyJ" not in str(kwargs)
    assert world.redis.get_source_token(job_id) == "sl.provider"

    seen = {}

    class Handler:
        async def download(self, source, temp_path, auth_token=None):
            seen["token"] = auth_token
            raise RuntimeError("stop after the download")

    monkeypatch.setattr(tasks, "get_source_handler", lambda source_type: Handler())
    monkeypatch.setattr(tasks, "get_es_client", lambda: SimpleNamespace())
    monkeypatch.setattr(tasks.process_conversion, "retry", lambda **kw: RuntimeError("retry"))
    with pytest.raises(RuntimeError):
        tasks.process_conversion.run(**kwargs)
    assert seen["token"] == "sl.provider"
    assert world.redis.get_source_token(job_id) == "sl.provider"  # a failed download keeps it for the retry

    class Good:
        async def download(self, source, temp_path, auth_token=None):
            path = temp_path / "a.pdf"
            path.write_bytes(b"%PDF-1.4")
            seen["token2"] = auth_token
            return path

    monkeypatch.setattr(tasks, "get_source_handler", lambda source_type: Good())
    monkeypatch.setattr(tasks, "should_split_pdf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RuntimeError):
        tasks.process_conversion.run(**kwargs)
    assert seen["token2"] == "sl.provider"
    assert world.redis.get_source_token(job_id) is None
