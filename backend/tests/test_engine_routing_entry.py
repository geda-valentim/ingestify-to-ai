"""
Where routed work enters and how the local worker runs it (spec 0003, slice 3b):
zero-config parity, /transcribe, /upload and /convert with and without a route, the
audio diversion inside process_conversion, the local executor's claim / heartbeat /
settle (never self.retry), the admin routing API, the job page signals and the CLI
step syntax.
"""

import asyncio
import io
import sys
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from api import routes
from api import routing_admin_routes as admin
from api.projects_api import LocationFields
from shared.engines import dispatch, ledger, routing
from shared.models import AdminAudit, EngineUsage, FeatureRoute, Job, JobDispatch, JobStatus, User
from workers import tasks
from workers.engines import local, watchdog
from tests._engines_world import ALICE, ROOT, World

LOCAL = "eng-local"


class FakeMinio:
    bucket_uploads = "ingestify-uploads"
    bucket_audio = "ingestify-audio"

    def upload_file(self, **kwargs):
        pass


@pytest.fixture
def world(monkeypatch, tmp_path):
    w = World(monkeypatch, tmp_path)
    monkeypatch.setattr(routes, "SessionLocal", w.Session)
    monkeypatch.setattr(routes, "get_redis_client", lambda: w.redis)
    monkeypatch.setattr(routes, "get_minio_client", lambda: FakeMinio())
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    w.applied, w.delayed = [], []
    monkeypatch.setattr(tasks.process_conversion, "apply_async", lambda **kw: w.applied.append(kw))
    monkeypatch.setattr(tasks.process_conversion, "delay", lambda **kw: w.delayed.append(kw))
    monkeypatch.setattr(routes, "_engine_celery", lambda: w.celery)
    yield w
    w.close()


def user(world, user_id):
    db = world.Session()
    return db, db.get(User, user_id)


def upload(name, data=None, content_type="audio/mpeg"):
    data = data or b"ID3" + name.encode() + b"\0" * 512  # distinct per name: no duplicate detection
    return UploadFile(file=io.BytesIO(data), filename=name, headers={"content-type": content_type})


def transcribe(world, user_id=ALICE, name="aula.mp3"):
    db, who = user(world, user_id)
    try:
        return asyncio.run(routes.transcribe_audio(
            file=upload(name), name=None, tags=None, language="pt", include_timestamps=True,
            include_word_timestamps=False, output_format="markdown", purge_source=False,
            location=LocationFields(project="Engines"),
            current_user=who, db=db))
    finally:
        db.close()


def upload_endpoint(world, name="aula.mp3", content_type="audio/mpeg"):
    db, who = user(world, ALICE)
    try:
        return asyncio.run(routes.upload_and_convert(file=upload(name, content_type=content_type), name=None,
                                                     tags=None, docling_preset="fast",
                                                     location=LocationFields(project="Engines"), current_user=who, db=db))
    finally:
        db.close()


def convert_endpoint(world, name="aula.mp3"):
    db, who = user(world, ALICE)
    try:
        return asyncio.run(routes.convert_document(source_type="file", source=None, file=upload(name), name=None,
                                                   tags=None, authorization=None,
                                                   location=LocationFields(project="Engines"), current_user=who, db=db))
    finally:
        db.close()


# --- zero-config parity ---------------------------------------------------------------


def test_without_a_route_transcribe_enqueues_exactly_as_today(world):
    response = transcribe(world)

    [call] = world.applied
    assert call["queue"] == "ingestify-audio"
    assert set(call["kwargs"]) == {"job_id", "source_type", "source", "options"}
    assert call["kwargs"]["job_id"] == str(response.job_id) and call["kwargs"]["source_type"] == "file"
    assert call["kwargs"]["options"] == {
        "language": "pt", "include_timestamps": True, "include_word_timestamps": False, "output_format": "markdown",
        "media_kind": "audio", "is_audio": True, "purge_source": False,
    }
    assert world.count(JobDispatch) == 0 and world.count(EngineUsage) == 0
    assert world.celery.sent == []


def test_without_a_route_upload_and_convert_audio_run_in_the_worker_as_today(world):
    upload_endpoint(world)
    convert_endpoint(world, name="talk.wav")
    first, second = world.delayed
    assert first["options"] == {"docling_preset": "fast"} and "usage_id" not in first
    assert set(second) == {"job_id", "source_type", "source", "options"}
    assert world.count(JobDispatch) == 0 and world.count(EngineUsage) == 0 and world.celery.sent == []


def test_without_a_route_process_conversion_still_retries(world, monkeypatch):
    job_id = world.add_job()
    source = world.tmp / "audio" / job_id / "aula.mp3"
    retried = []

    def boom(*a, **k):
        raise RuntimeError("whisper exploded")

    class Retry(Exception):
        pass

    def fake_retry(exc=None, countdown=None, **kw):
        retried.append(countdown)
        raise Retry()

    import workers.audio as audio_pkg
    monkeypatch.setattr(audio_pkg, "transcribe_with_gpu_fallback", boom)
    monkeypatch.setattr(tasks, "get_es_client", lambda: SimpleNamespace())
    monkeypatch.setattr(tasks.process_conversion, "retry", fake_retry)

    with pytest.raises(Retry):
        tasks.process_conversion.run(job_id=job_id, source_type="file", source=str(source), options={"is_audio": True})
    assert retried == [60]
    assert world.job(job_id).status == JobStatus.FAILED
    assert world.count(JobDispatch) == 0 and world.count(EngineUsage) == 0


def test_modal_is_never_imported():
    import api.main  # noqa: F401
    import workers.celery_app  # noqa: F401
    import workers.engines.tasks  # noqa: F401
    import workers.engines.watchdog  # noqa: F401
    assert "modal" not in sys.modules


def test_without_a_route_the_watchdog_does_nothing(world):
    world.add_item()  # even a stray row: no route, nothing to watch
    with world.Session() as db:
        db.query(JobDispatch).delete()
        db.commit()
    assert watchdog.watchdog_round(celery=world.celery, session_factory=world.Session) is None
    assert world.celery.sent == []


def test_route_lookup_errors_read_as_no_route(world):
    def broken():
        raise RuntimeError("database down")

    assert routing.get_route("transcription", session_factory=broken) is None


# --- entering the backlog ------------------------------------------------------------------


def test_with_a_route_transcribe_joins_the_backlog(world):
    world.set_route([LOCAL])
    world.dispatcher_alive()
    response = transcribe(world)

    assert world.applied == []
    with world.Session() as db:
        d = db.query(JobDispatch).one()
        assert (d.state, d.subject_id, d.remote_allowed, d.user_id) == ("probing", str(response.job_id), False, ALICE)
        assert d.payload["today_queue"] == "ingestify-audio"
        assert set(d.payload["kwargs"]) == {"job_id", "source_type", "source", "options"}
        dispatch_id = d.id
    [probe_call] = world.celery.named(dispatch.PROBE_TASK)
    assert probe_call.args == [dispatch_id] and probe_call.queue == "ingestify-dispatch"
    assert world.count(EngineUsage) == 0


def test_a_routed_job_keeps_its_project_and_the_backlog_never_carries_it(world):
    # Spec 0004 x spec 0003: the location lives on the MAIN job row, written before
    # dispatch.submit; the allowlisted backlog payload stays free of it.
    world.set_route([LOCAL])
    world.dispatcher_alive()
    response = transcribe(world)

    assert response.project.name == "Engines"
    with world.Session() as db:
        job = db.get(Job, str(response.job_id))
        assert job.project_id == response.project.id and job.folder_id is None
        d = db.query(JobDispatch).one()
        assert "project" not in repr(d.payload) and job.project_id not in repr(d.payload)


def test_admins_items_may_go_remote(world):
    world.set_route([LOCAL])
    world.dispatcher_alive()
    transcribe(world, user_id=ROOT)
    with world.Session() as db:
        assert db.query(JobDispatch).one().remote_allowed is True


def test_with_a_route_upload_and_convert_send_audio_to_the_backlog_and_documents_as_today(world):
    world.set_route([LOCAL])
    world.dispatcher_alive()
    upload_endpoint(world)
    convert_endpoint(world, name="talk.m4a")
    upload_endpoint(world, name="report.pdf", content_type="application/pdf")

    assert len(world.delayed) == 1 and world.delayed[0]["source"].endswith("report.pdf")
    with world.Session() as db:
        rows = db.query(JobDispatch).all()
        assert len(rows) == 2
        for d in rows:
            assert d.payload["kwargs"]["options"] == dispatch.DEFAULT_TRANSCRIPTION_OPTIONS
            assert d.payload["today_queue"] == "ingestify"


def test_dispatcher_down_with_local_direct_publishes_with_a_usage_row(world):
    world.set_route([LOCAL])  # the dispatcher has never been seen
    response = transcribe(world)

    [run] = world.celery.local_runs()
    assert run.queue == "ingestify-audio" and run.kwargs["job_id"] == str(response.job_id)
    usage = world.usage(run.kwargs["usage_id"])
    assert (usage.status, usage.placed_by, usage.attempt, usage.reserved_usd) == ("reserved", "fallback", 1, 0)
    assert usage.published_at is not None
    with world.Session() as db:
        assert db.query(JobDispatch).one().state == "bypassed"


def test_dispatcher_down_with_hold_waits_in_the_backlog(world):
    world.set_route([LOCAL], dispatcher_fallback="hold")
    transcribe(world)
    assert world.celery.local_runs() == [] and world.count(EngineUsage) == 0
    with world.Session() as db:
        assert db.query(JobDispatch).one().state == "probing"


def test_when_the_broker_is_down_submit_fails_like_today_and_leaves_nothing(world):
    world.set_route([LOCAL])
    world.dispatcher_alive()

    def down(*a, **k):
        raise ConnectionError("redis down")

    world.celery.send_task = down
    with pytest.raises(HTTPException) as exc:
        transcribe(world)
    assert exc.value.status_code == 500
    assert world.count(JobDispatch) == 0 and world.count(EngineUsage) == 0


def test_audio_downloaded_by_the_worker_is_diverted_to_the_backlog(world, monkeypatch):
    world.set_route([LOCAL])
    world.dispatcher_alive()
    job_id = world.add_job(status=JobStatus.PENDING, name="podcast")

    class Handler:
        async def download(self, source, temp_path, auth_token=None):
            path = temp_path / "episode.mp3"
            path.write_bytes(b"ID3" + b"\0" * 100)
            return path

    import workers.audio as audio_pkg
    monkeypatch.setattr(tasks, "get_source_handler", lambda source_type: Handler())
    monkeypatch.setattr(tasks, "get_es_client", lambda: SimpleNamespace())
    monkeypatch.setattr(audio_pkg, "transcribe_with_gpu_fallback",
                        lambda *a, **k: pytest.fail("must not transcribe in the worker"))

    result = tasks.process_conversion.run(job_id=job_id, source_type="url", source="https://example.com/ep.mp3",
                                          options={}, auth_token="secret-token")

    assert result == {"job_id": job_id, "status": "queued"}
    moved = world.tmp / "audio" / job_id / "episode.mp3"
    assert moved.exists() and not (world.tmp / job_id / "episode.mp3").exists()
    job = world.job(job_id)
    assert job.status == JobStatus.PENDING and job.started_at is None
    assert world.redis.get_job_status(job_id)["status"] == "queued"
    with world.Session() as db:
        d = db.query(JobDispatch).one()
        assert d.state == "probing" and d.payload["kwargs"]["source"] == str(moved)
        assert "secret-token" not in str(d.payload)


# --- the local executor ------------------------------------------------------------------------


@pytest.fixture
def routed(world, monkeypatch):
    """One item placed on the local engine, and a process_conversion ready to run it"""
    world.set_route([LOCAL])
    item = world.add_item()
    world.tick()
    [run] = world.celery.local_runs()
    state = SimpleNamespace(transcribed=0, finished=[], fail=None)

    def transcribe_fn(*a, **k):
        state.transcribed += 1
        if state.fail:
            raise state.fail
        return {"word_count": 1, "duration": 1.0, "language": "pt", "device": "cpu"}, SimpleNamespace()

    def finish(job_id, result, **kwargs):
        state.finished.append(job_id)
        with world.Session() as db:
            job = db.get(Job, job_id)
            job.status, job.completed_at = JobStatus.COMPLETED, datetime.utcnow()
            db.commit()

    import workers.audio as audio_pkg
    monkeypatch.setattr(audio_pkg, "transcribe_with_gpu_fallback", transcribe_fn)
    monkeypatch.setattr(tasks, "finish_transcription", finish)
    monkeypatch.setattr(tasks, "get_es_client", lambda: SimpleNamespace())
    monkeypatch.setattr(tasks.process_conversion, "retry", lambda *a, **k: pytest.fail("self.retry with usage_id"))
    state.item, state.kwargs = item, run.kwargs
    state.run = lambda: tasks.process_conversion.run(**run.kwargs)
    return state


def test_a_routed_transcription_claims_runs_and_settles(world, routed):
    world.celery.sent.clear()
    assert routed.run()["status"] == "completed"
    usage, d = world.usage(routed.kwargs["usage_id"]), world.item(routed.item)
    assert (usage.status, usage.outcome, usage.actual_usd) == ("settled", "succeeded", 0)
    assert usage.output_persisted_at is not None and usage.measured_seconds is not None
    assert d.state == "done" and routed.finished == [d.job_id]
    assert world.celery.named(dispatch.TICK_TASK)  # the freed slot is offered at once


def test_a_redelivered_message_is_acknowledged_without_running(world, routed):
    routed.run()
    assert routed.run()["status"] == ledger.LOST
    assert routed.transcribed == 1


def test_a_routed_failure_never_retries_and_lets_the_backlog_decide(world, routed):
    routed.fail = RuntimeError("CUDA out of memory")
    assert routed.run()["status"] == "queued"
    usage, d = world.usage(routed.kwargs["usage_id"]), world.item(routed.item)
    assert (usage.outcome, usage.error_code, usage.counts_toward_attempts) == ("failed", "INTERNAL", True)
    assert (d.state, d.job_failures, d.priority) == ("waiting", 1, 0) and d.not_before is not None
    job = world.job(d.job_id)
    assert job.status == JobStatus.PENDING and job.started_at is None
    assert world.redis.get_job_status(d.job_id)["status"] == "queued"


def test_the_last_routed_failure_fails_the_job(world, routed):
    with world.Session() as db:
        db.get(JobDispatch, routed.item).job_failures = 2
        db.commit()
    routed.fail = RuntimeError("bad media")
    assert routed.run()["status"] == "failed"
    d = world.item(routed.item)
    assert (d.state, d.error_code) == ("failed", "engine_error")
    assert world.job(d.job_id).status == JobStatus.FAILED
    assert world.redis.get_job_status(d.job_id)["status"] == "failed"


def test_a_routed_timeout_fails_for_good_like_today(world, routed):
    from celery.exceptions import SoftTimeLimitExceeded
    routed.fail = SoftTimeLimitExceeded()
    assert routed.run()["status"] == "failed"
    usage, d = world.usage(routed.kwargs["usage_id"]), world.item(routed.item)
    assert (usage.error_code, d.state, d.error_code) == ("TIMEOUT", "failed", "TIMEOUT")


def test_a_job_deleted_meanwhile_is_not_completed(world, routed):
    def transcribe_then_delete(*a, **k):
        with world.Session() as db:
            db.query(Job).filter(Job.id == world.item(routed.item).job_id).delete()
            db.commit()
        return {"word_count": 1, "duration": 1.0, "language": "pt"}, SimpleNamespace()

    import workers.audio as audio_pkg
    audio_pkg.transcribe_with_gpu_fallback = transcribe_then_delete
    assert routed.run()["status"] == "cancelled"
    assert routed.finished == []
    assert world.usage(routed.kwargs["usage_id"]).outcome == "cancelled"


def test_the_heartbeat_thread_renews_the_claimed_row(world):
    world.set_route([LOCAL])
    item = world.add_item()
    world.tick()
    usage_id = world.item(item).usage_id
    ledger.claim(usage_id, "me", session_factory=world.Session, now=world.now - timedelta(minutes=5))
    beat = local.UsageHeartbeat(usage_id, "me", interval=0.05, session_factory=world.Session).start()
    time.sleep(0.3)
    beat.stop()
    assert world.usage(usage_id).heartbeat_at > world.now - timedelta(minutes=1)


# --- admin API ------------------------------------------------------------------------------------


def _request():
    return SimpleNamespace(headers={"authorization": "Bearer t"}, client=SimpleNamespace(host="10.0.0.1"))


def put(world, feature="transcription", **body):
    db, root = user(world, ROOT)
    try:
        return asyncio.run(admin.put_route(feature, admin.RouteUpdate(**body), _request(), admin_user=root, db=db))
    finally:
        db.close()


def test_put_route_saves_a_local_route_and_audits_it(world, monkeypatch):
    monkeypatch.setattr(admin, "_alive_by_feature", lambda: {})
    view = put(world, steps=[{"engine_ids": ["local"]}])
    assert view["steps"][0]["engine_ids"] == [LOCAL] and view["steps"][0]["position"] == 1
    assert view["version"] == 1 and view["state"] == "active"
    assert any("dispatcher" in w for w in view["warnings"])  # worker-dispatch not running
    with world.Session() as db:
        audit = db.query(AdminAudit).one()
        assert (audit.action, audit.target_type, audit.target_id, audit.actor_user_id) == \
            ("route.set", "route", "transcription", ROOT)

    with pytest.raises(HTTPException) as exc:
        put(world, steps=[{"engine_ids": ["local"]}], version=0)
    assert exc.value.status_code == 409


@pytest.mark.parametrize("body, status", [
    ({"steps": [{"engine_ids": ["fake_1"]}]}, 422),  # remote, admins only, no local step
    ({"steps": [{"engine_ids": ["local"]}, {"engine_ids": ["fake_1"]}]}, 409),  # remote: slice 4a
    ({"steps": [{"engine_ids": ["nope"]}]}, 422),
    ({"steps": [{"engine_ids": ["local"]}, {"engine_ids": ["local"]}]}, 422),
])
def test_put_route_validation(world, body, status):
    world.add_remote("fake_1")
    with pytest.raises(HTTPException) as exc:
        put(world, **body)
    assert exc.value.status_code == status
    assert world.count(FeatureRoute) == 0


def test_a_route_needs_capacity_on_its_engines(world):
    from shared.models import Engine
    with world.Session() as db:
        db.get(Engine, LOCAL).config = {"features": {}}
        db.commit()
    with pytest.raises(HTTPException) as exc:
        put(world, steps=[{"engine_ids": ["local"]}])
    assert exc.value.status_code == 422 and "no capacity" in exc.value.detail


def test_document_pages_and_vision_can_be_routed_on_local_engines_only(world, monkeypatch):
    """Slice 8: every feature has a routed entry; remote steps stay transcription-only"""
    from shared.models import Engine
    monkeypatch.setattr(admin, "_alive_by_feature", lambda: {})
    with world.Session() as db:
        local = db.get(Engine, LOCAL)
        local.config = {**local.config, "features": {**local.config["features"],
                                                     "vision": {"gpu_ref": "gpu0", "workers": 1},
                                                     "document_conversion": {"workers": 2}}}
        db.commit()
    assert put(world, feature="vision", steps=[{"engine_ids": ["local"]}])["state"] == "active"
    assert put(world, feature="document_conversion", steps=[{"engine_ids": ["local"]}])["state"] == "active"

    world.add_remote("fake_1", config={"features": {"vision": {"gpu_type": "L4", "workers": 1}}})
    with pytest.raises(HTTPException) as exc:
        put(world, feature="vision", steps=[{"engine_ids": ["local"]}, {"engine_ids": ["fake_1"]}])
    assert exc.value.status_code == 422 and "local engines only" in exc.value.detail


def test_opening_remote_work_to_everyone_needs_the_password(world):
    body = dict(steps=[{"engine_ids": ["local"]}], remote_allowed_for="all", user_period_limit_usd=5,
                remote_data_notice="Media may be sent to a cloud provider.")
    with pytest.raises(HTTPException) as exc:
        put(world, **body)
    assert exc.value.status_code == 403
    assert put(world, current_password="pw", **body)["remote_allowed_for"] == "all"


def test_delete_route_drains(world):
    put(world, steps=[{"engine_ids": ["local"]}])
    db, root = user(world, ROOT)
    try:
        view = asyncio.run(admin.delete_route("transcription", _request(), admin_user=root, db=db))
        assert view["state"] == "draining"
        with pytest.raises(HTTPException) as exc:
            asyncio.run(admin.delete_route("vision", _request(), admin_user=root, db=db))
        assert exc.value.status_code == 404
    finally:
        db.close()
    assert routing.get_route("transcription", session_factory=world.Session).state == "draining"


def test_admin_views(world, monkeypatch):
    monkeypatch.setattr(admin, "_alive_by_feature", lambda: {"transcription": [{"hostname": "a"}]})
    world.set_route([LOCAL])
    world.add_item(wait=30)
    db, root = user(world, ROOT)
    try:
        listed = {v["feature"]: v for v in asyncio.run(admin.list_routes(admin_user=root, db=db))}
        assert listed["vision"]["implicit"] is True and listed["transcription"]["implicit"] is False
        assert listed["transcription"]["backlog"]["waiting"] == 1
        assert listed["transcription"]["backlog"]["oldest_wait_seconds"] >= 30

        status = asyncio.run(admin.engines_status(admin_user=root, db=db))
        assert status["dispatcher"]["epoch"] == 0 and status["dispatcher"]["dispatcher_seen_at"] is None
        [row] = [r for r in status["engines"] if r["engine"] == "local"]
        assert (row["capacity"], row["in_flight"], row["workers_alive"]) == (2, 0, 1)
        assert status["backlog"]["transcription"]["by_state"]["waiting"] == 1
    finally:
        db.close()


# --- the job page ---------------------------------------------------------------------------------


def test_the_job_page_says_where_and_why(world):
    world.set_route([LOCAL])
    item = world.add_item()
    job_id = world.item(item).job_id
    with world.Session() as db:
        assert dispatch.job_signal(db, job_id) == (None, "in_queue")
    world.tick()
    with world.Session() as db:
        assert dispatch.job_signal(db, job_id) == ({"kind": "local"}, "starting")
        assert dispatch.job_signal(db, "unrouted") == (None, None)

    world.redis.set_job_status(job_id=job_id, job_type="main", status="queued")
    db, alice = user(world, ALICE)
    try:
        response = asyncio.run(routes.get_job_status(job_id, current_user=alice, owned_job=db.get(Job, job_id), db=db))
    finally:
        db.close()
    assert response.engine.kind == "local" and response.queue_reason == "starting"


# --- CLI step syntax -----------------------------------------------------------------------------


def test_cli_steps_parse():
    step = routing.parse_step("modal_1,modal_2 fill_first min_wait=600 min_backlog=20 scale_out=120 cap=1.50/day")
    assert step.engine_ids == ["modal_1", "modal_2"] and step.group_strategy == "fill_first"
    assert step.when.min_wait_seconds == 600 and step.when.min_backlog == 20
    assert step.scale_out_after_seconds == 120 and str(step.spend_cap.usd) == "1.50"
    assert routing.parse_step("local").engine_ids == ["local"]
    with pytest.raises(ValueError):
        routing.parse_step("local bogus=1")
