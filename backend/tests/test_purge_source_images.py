"""
`purge_source` on every image route (POST /images/*).

Where an image job's original lives (see `shared.job_source`, "Image jobs"):

- the local handoff `{TEMP_STORAGE_PATH}/images/{job_id}/` (native tasks, and the
  Full / face worker's download of its durable source);
- native describe / ocr / analyze: the stored result embeds it
  (`image.image_base64` in Redis and `images/{job_id}/result.json`);
- Full / face analysis: `images/{job_id}/source`, the normalized full-size
  preview `images/{job_id}/preview/...`, and that preview embedded in the report.

With `purge_source=true` every one of them is gone once the job settles and the
inference result is kept; `GET /jobs/{id}` reports `source_available` /
`source_deleted_at` truthfully, and `DELETE /jobs/{id}/source` works for image jobs.

SQLite with the real models, fakeredis through the real RedisClient, an in-memory
object store, and the real vision worker body (`workers.vision_tasks._run`) with a
stub model, run in-process by the dispatch seam.
"""
import base64
import io
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker)
from api import face_routes, image_full_routes, image_routes, routes
from shared import projects as projects_module
from shared.auth import create_access_token
from shared.config import get_settings
from shared.database import Base, get_db
from shared.engines import dispatch as engine_dispatch
from shared.models import ImageAnalysisRun, Job, JobStatus, Project, User

ALICE = "user-alice"


def _png(size=(8, 8)):
    from PIL import Image

    data = io.BytesIO()
    Image.new("RGB", size, "white").save(data, "PNG")
    return data.getvalue()


PNG = _png()
PNG_B64 = base64.b64encode(PNG).decode("ascii")
MODEL_INFO = {"model_id": "stub", "revision": "r1", "device": "cpu", "dtype": "float32"}


class Storage:
    """In-memory MinIO: one namespace, keyed by object name."""
    bucket_uploads = "ingestify-uploads"
    bucket_audio = "ingestify-audio"
    bucket_pages = "ingestify-pages"
    bucket_results = "ingestify-results"

    def __init__(self):
        self.objects = {}
        self.refuse_delete = None  # None | callable(object_name) -> True to refuse
        self.on_upload = None  # callable(object_name), called after the write

    def upload_file(self, bucket_name, object_name, file_data=None, content_type=None, **kwargs):
        self.objects[object_name] = file_data
        if self.on_upload:
            self.on_upload(object_name)
        return object_name

    def download_file(self, bucket_name, object_name, file_path=None):
        if object_name not in self.objects:
            raise KeyError(object_name)
        return self.objects[object_name]

    def list_objects(self, bucket_name, prefix=""):
        return [k for k in self.objects if k.startswith(prefix)]

    def delete_file(self, bucket_name, object_name):
        if self.refuse_delete and self.refuse_delete(object_name):
            return False  # what MinIOClient answers on an S3Error
        self.objects.pop(object_name, None)
        return True

    def delete_folder(self, bucket_name, folder_prefix):
        if self.refuse_delete and self.refuse_delete(folder_prefix):
            return False
        for key in [k for k in self.objects if k.startswith(folder_prefix)]:
            del self.objects[key]
        return True


class Describer:
    """The stub model behind the real `_run` of workers.vision_tasks."""
    fail = None  # None | "typed" (VisionError, returned) | "crash" (raised)

    def _maybe_fail(self):
        if self.fail == "typed":
            from workers.vision.errors import VisionError
            raise VisionError("model unavailable")
        if self.fail == "crash":
            raise RuntimeError("worker crashed")

    def describe(self, path, options):
        self._maybe_fail()
        return {"description": "a white square", "task": (options or {}).get("task", "<MORE_DETAILED_CAPTION>"),
                "width": 8, "height": 8, "duration_ms": 3}

    def ocr(self, path, options):
        self._maybe_fail()
        return {"text": "HELLO", "lines": [], "width": 8, "height": 8, "duration_ms": 3}

    def analyze(self, path, options):
        self._maybe_fail()
        return {"task": options["task"], "text": "a square", "output": {options["task"]: "a square"},
                "regions": [], "request": options, "width": 8, "height": 8, "duration_ms": 3}

    def info(self):
        return MODEL_INFO


class FakeAsyncResult:
    def __init__(self, result):
        self.id, self.result = "task-1", result

    def ready(self):
        return True


@pytest.fixture
def env(fake_redis, tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(User(id=ALICE, email="alice@example.com", username="alice", hashed_password="x", is_active=True))
        project = Project(user_id=ALICE, name="Images", name_key=projects_module.name_key("Images"))
        db.add(project)
        db.commit()

    storage = Storage()
    from workers import vision_tasks as worker_module
    # The route and the worker keep a module-level settings object, which another
    # test may have made distinct from get_settings() (shared.job_source)
    for settings in {id(s): s for s in (get_settings(), image_routes.settings, worker_module.settings)}.values():
        monkeypatch.setattr(settings, "temp_storage_path", str(tmp_path))
        monkeypatch.setattr(settings, "enable_image_description", True)
    monkeypatch.setattr(projects_module.get_settings(), "upload_fallback_project", "")

    import shared.minio_client as minio_module
    import shared.redis_client as redis_module
    from shared import image_analysis
    from shared.datalake import service
    from workers import image_full_tasks, vision_tasks
    from workers.vision import factory as vision_factory

    for module in (routes, image_routes):
        monkeypatch.setattr(module, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(redis_module, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(minio_module, "get_minio_client", lambda: storage)
    monkeypatch.setattr(routes, "get_minio_client", lambda: storage)
    monkeypatch.setattr(image_full_routes, "get_minio_client", lambda: storage)
    monkeypatch.setattr(image_full_tasks, "get_minio_client", lambda: storage)
    for module in (vision_tasks, image_analysis, image_full_tasks):
        monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setattr(service, "enqueue_export", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_full_tasks, "dispatch", lambda *args: None)
    monkeypatch.setattr(face_routes, "require_faces", lambda mode: {"models": []})
    monkeypatch.setattr(image_routes, "_place_vision", lambda *args: engine_dispatch.Placement("today"))

    describer = Describer()
    monkeypatch.setattr(vision_tasks, "get_image_describer", lambda: describer)
    monkeypatch.setattr(vision_factory, "get_image_describer", lambda *a, **k: describer)

    queued = []

    def run_task(call):
        kind = call["kind"]
        options = {"task": call["task"]} if kind == "describe" else call.get("options")
        try:
            return vision_tasks._run(kind, call["job_id"], call["image_path"], options)
        except Exception as exc:  # noqa: BLE001 - what Celery would hand the route
            return exc

    def dispatch(kind, **kwargs):
        call = {"kind": kind, **kwargs}
        if env_ns.run_now:
            return FakeAsyncResult(run_task(call))
        queued.append(call)
        return FakeAsyncResult(None)

    monkeypatch.setattr(image_routes, "_dispatch_vision_task", dispatch)

    def db_dependency():
        with factory() as db:
            yield db

    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(face_routes.router)
    app.include_router(image_routes.router)
    app.dependency_overrides[get_db] = db_dependency
    env_ns = SimpleNamespace(client=TestClient(app), Session=factory, storage=storage, redis=fake_redis,
                             tmp=tmp_path, project=project, describer=describer, queued=queued,
                             run_task=run_task, run_now=True)
    yield env_ns
    engine.dispose()


def jwt():
    return {"Authorization": f"Bearer {create_access_token({'sub': ALICE})}"}


def job(env, job_id) -> Job:
    with env.Session() as db:
        found = db.get(Job, job_id)
        if found is not None:
            _ = found.configuration_row  # load before the session closes
        return found


def handoff(env, job_id):
    return env.tmp / "images" / job_id


def status(env, job_id):
    r = env.client.get(f"/jobs/{job_id}", headers=jwt())
    assert r.status_code == 200, r.text
    return r.json()


def run_full_worker(job_id):
    from workers.image_full_tasks import run_full_image_task
    run_full_image_task.run(job_id=job_id)


# ---------------------------------------------------------------------------
# The eight routes
# ---------------------------------------------------------------------------

def _post(env, route, purge, key=None):
    """POST one image route; `purge` is the raw value sent (None: omitted)."""
    headers = {**jwt(), **({"Idempotency-Key": key or str(uuid4())} if route in FULL_ROUTES else {})}
    multipart = "/upload" in route
    if multipart:
        data = {"project_id": env.project.id}
        if route == "/images/analyze/upload/full":
            data["mode"] = "full"
        if purge is not None:
            data["purge_source"] = purge
        path = route.removesuffix("/full")
        return env.client.post(path, headers=headers, data=data, files={"file": ("foto.png", PNG, "image/png")})
    body = {"image_base64": PNG_B64, "filename": "foto.png", "project_id": env.project.id}
    if route == "/images/analyze/full":
        body["mode"] = "full"
    if purge is not None:
        body["purge_source"] = purge
    return env.client.post(route.removesuffix("/full"), headers=headers, json=body)


SYNC_ROUTES = ["/images/describe", "/images/describe/upload", "/images/ocr", "/images/ocr/upload"]
QUEUED_ROUTES = ["/images/analyze", "/images/analyze/upload"]
FULL_ROUTES = ["/images/analyze/full", "/images/analyze/upload/full", "/images/faces", "/images/faces/upload"]
ALL_ROUTES = SYNC_ROUTES + QUEUED_ROUTES + FULL_ROUTES


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_every_image_route_accepts_purge_source_and_records_it_on_the_job(env, route):
    r = _post(env, route, "true" if route.endswith(("/upload", "/upload/full")) else True)

    assert r.status_code in (200, 202), r.text
    created = job(env, r.json()["job_id"])
    assert created.source_type == "image"
    assert created.purge_source is True
    assert created.configuration_row.options["purge_source"] is True  # what was requested


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_every_image_route_rejects_a_non_bool_purge_source(env, route):
    r = _post(env, route, "maybe")

    assert r.status_code == 422, r.text
    with env.Session() as db:
        assert db.query(Job).count() == 0, "an invalid request must not create a job"


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_purge_source_defaults_to_keeping_the_original(env, route):
    r = _post(env, route, None)

    assert r.status_code in (200, 202), r.text
    assert not job(env, r.json()["job_id"]).purge_source


# ---------------------------------------------------------------------------
# Native describe / ocr / analyze
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route", SYNC_ROUTES)
def test_sync_purge_deletes_every_copy_once_the_job_completes(env, route):
    r = _post(env, route, "true" if route.endswith("/upload") else True)

    assert r.status_code == 200, r.text
    body = r.json()
    job_id = body["job_id"]
    # The synchronous answer still echoes the request's own bytes
    assert base64.b64decode(body["image_base64"]) == PNG

    done = job(env, job_id)
    assert done.status == JobStatus.COMPLETED
    assert done.source_deleted_at is not None
    assert not handoff(env, job_id).exists()
    stored = json.loads(env.storage.objects[done.minio_result_path])
    assert stored["image"]["image_base64"] is None
    assert stored["markdown"]  # the inference result is kept
    assert env.redis.get_job_result(job_id)["image"]["image_base64"] is None

    s = status(env, job_id)
    assert s["source_available"] is False
    assert s["source_deleted_at"]
    assert s["source_deletable"] is False
    assert env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 404


def test_without_purge_the_result_keeps_the_image_and_the_original_is_reported(env):
    r = _post(env, "/images/describe/upload", None)
    job_id = r.json()["job_id"]

    done = job(env, job_id)
    assert done.source_deleted_at is None
    assert not handoff(env, job_id).exists()  # the task's own cleanup, as before
    stored = json.loads(env.storage.objects[done.minio_result_path])
    assert base64.b64decode(stored["image"]["image_base64"]) == PNG

    s = status(env, job_id)
    assert s["source_available"] is True
    assert s["source_deleted_at"] is None
    assert s["source_deletable"] is True


@pytest.mark.parametrize("route", QUEUED_ROUTES)
def test_async_purge_waits_for_the_task_and_then_deletes(env, route):
    env.run_now = False
    r = _post(env, route, "true" if route.endswith("/upload") else True)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    # Queued: the handoff is the original and it is still needed
    assert handoff(env, job_id).exists()
    s = status(env, job_id)
    assert s["source_available"] is True and s["source_deletable"] is False
    blocked = env.client.delete(f"/jobs/{job_id}/source", headers=jwt())
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "JOB_STILL_PROCESSING"
    assert handoff(env, job_id).exists()

    env.run_task(env.queued.pop())

    done = job(env, job_id)
    assert done.status == JobStatus.COMPLETED
    assert done.source_deleted_at is not None
    assert not handoff(env, job_id).exists()
    assert json.loads(env.storage.objects[done.minio_result_path])["image"]["image_base64"] is None
    s = status(env, job_id)
    assert s["source_available"] is False and s["source_deleted_at"]


@pytest.mark.parametrize("failure", ["typed", "crash"])
def test_a_failed_task_purges_too(env, failure):
    env.describer.fail = failure
    r = _post(env, "/images/ocr/upload", "true")

    assert r.status_code in (500, 503), r.text
    job_id = r.json()["detail"]["job_id"]
    failed = job(env, job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.source_deleted_at is not None
    assert not handoff(env, job_id).exists()
    s = status(env, job_id)
    assert s["source_available"] is False and s["source_deleted_at"]


def test_a_failed_task_without_purge_reports_no_original_left(env):
    """The handoff was the only copy and the task removed it: say so, never "available"."""
    env.describer.fail = "typed"
    r = _post(env, "/images/ocr/upload", None)
    job_id = r.json()["detail"]["job_id"]

    s = status(env, job_id)
    assert s["source_available"] is False
    assert s["source_deleted_at"] is None
    assert env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 404


def test_a_request_that_never_reached_a_worker_records_the_purge(env, monkeypatch):
    def broker_down(kind, **kwargs):
        raise ConnectionError("broker down")

    monkeypatch.setattr(image_routes, "_dispatch_vision_task", broker_down)
    r = _post(env, "/images/describe/upload", "true")

    assert r.status_code == 503
    job_id = r.json()["detail"]["job_id"]
    assert job(env, job_id).source_deleted_at is not None
    assert not handoff(env, job_id).exists()


def test_delete_source_strips_a_native_result_and_keeps_the_inference(env):
    job_id = _post(env, "/images/describe", None).json()["job_id"]
    result_path = job(env, job_id).minio_result_path

    r = env.client.delete(f"/jobs/{job_id}/source", headers=jwt())

    assert r.status_code == 200, r.text
    assert r.json()["source_deleted"] is True and r.json()["source_deleted_at"]
    stored = json.loads(env.storage.objects[result_path])
    assert stored["image"]["image_base64"] is None
    assert stored["image"]["description"] == "a white square"
    assert env.redis.get_job_result(job_id)["image"]["image_base64"] is None
    s = status(env, job_id)
    assert s["source_available"] is False and s["source_deleted_at"]
    assert env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 404


# ---------------------------------------------------------------------------
# Full / face analysis
# ---------------------------------------------------------------------------

def _full_objects(env, job_id):
    return {k for k in env.storage.objects if k.startswith(f"images/{job_id}/")}


def test_full_purge_deletes_source_preview_and_embedded_copy(env):
    r = _post(env, "/images/analyze/full", True)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert f"images/{job_id}/source" in env.storage.objects

    run_full_worker(job_id)

    done = job(env, job_id)
    assert done.status == JobStatus.COMPLETED
    assert done.source_deleted_at is not None
    objects = _full_objects(env, job_id)
    assert f"images/{job_id}/source" not in objects
    assert not [k for k in objects if "/preview/" in k]
    report = json.loads(env.storage.objects[done.minio_result_path])
    assert report["image"]["image_base64"] is None
    assert report["image"]["coverage"]["task_families_completed"] == 15  # the result is kept
    assert env.redis.get_job_result(job_id)["image"]["image_base64"] is None
    assert not handoff(env, job_id).exists()
    with env.Session() as db:
        run = db.get(ImageAnalysisRun, job_id)
        assert run.source_path == "" and run.preview_path is None

    s = status(env, job_id)
    assert s["source_available"] is False and s["source_deleted_at"]


def test_full_without_purge_keeps_its_copies_until_delete_source(env):
    job_id = _post(env, "/images/analyze/upload/full", None).json()["job_id"]

    blocked = env.client.delete(f"/jobs/{job_id}/source", headers=jwt())
    assert blocked.status_code == 409  # pending: the worker still needs it

    run_full_worker(job_id)
    done = job(env, job_id)
    assert done.status == JobStatus.COMPLETED and done.source_deleted_at is None
    old_report = done.minio_result_path
    assert json.loads(env.storage.objects[old_report])["image"]["image_base64"]
    assert f"images/{job_id}/source" in env.storage.objects
    s = status(env, job_id)
    assert s["source_available"] is True and s["source_deletable"] is True

    r = env.client.delete(f"/jobs/{job_id}/source", headers=jwt())

    assert r.status_code == 200, r.text
    after = job(env, job_id)
    objects = _full_objects(env, job_id)
    assert f"images/{job_id}/source" not in objects
    assert not [k for k in objects if "/preview/" in k]
    # The report is named after its content: rewritten under its new hash
    assert after.minio_result_path != old_report and old_report not in env.storage.objects
    report = json.loads(env.storage.objects[after.minio_result_path])
    assert report["image"]["image_base64"] is None
    assert report["image"]["coverage"]["task_families_completed"] == 15
    s = status(env, job_id)
    assert s["source_available"] is False and s["source_deleted_at"]
    assert env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 404


def test_a_cancelled_full_analysis_purges(env):
    from shared import image_analysis as lifecycle

    job_id = _post(env, "/images/analyze/full", True).json()["job_id"]
    holder = str(uuid4())
    fence, *_ = lifecycle.claim(job_id, holder)
    lifecycle.finish(job_id, holder, fence, env.storage, reason="cancelled")

    cancelled = job(env, job_id)
    assert cancelled.status == JobStatus.CANCELLED
    assert cancelled.source_deleted_at is not None
    assert f"images/{job_id}/source" not in env.storage.objects


@pytest.mark.parametrize("route", ["/images/analyze/full", "/images/faces"])
@pytest.mark.parametrize("first, replay", [(None, True), (True, False)])
def test_a_replayed_key_with_another_purge_source_returns_the_attempt_unchanged(env, route, first, replay):
    """purge_source is not part of the Idempotency-Key fingerprint (documented)."""
    one = _post(env, route, first, key="same-key")
    two = _post(env, route, replay, key="same-key")

    assert one.status_code == two.status_code == 202, two.text
    assert two.json()["job_id"] == one.json()["job_id"]
    assert two.json()["attempt"] == one.json()["attempt"] == 1
    assert bool(job(env, one.json()["job_id"]).purge_source) is bool(first)


# ---------------------------------------------------------------------------
# Review fixes: lost leases, report rewrite, cache write-back, Redis, retry
# ---------------------------------------------------------------------------

def _previews(env, job_id):
    return [k for k in env.storage.objects if k.startswith(f"images/{job_id}/preview/")]


def test_a_worker_that_lost_its_lease_never_leaves_its_preview_behind(env):
    """The reconciler fenced the run and the job was purged while the old worker
    was about to publish its preview: the preview it wrote must go too."""
    from datetime import datetime

    job_id = _post(env, "/images/analyze/full", True).json()["job_id"]

    def fence_and_purge(name):
        if "/preview/" not in name:
            return
        env.storage.on_upload = None
        with env.Session() as db:
            run = db.get(ImageAnalysisRun, job_id)
            run.fence += 1
            run.status = "cancelled"
            env.storage.objects.pop(f"images/{job_id}/source", None)  # what the purge deleted
            run.source_path, run.preview_path = "", None
            job_row = db.get(Job, job_id)
            job_row.status = JobStatus.CANCELLED
            job_row.source_deleted_at = datetime.utcnow()
            db.commit()

    env.storage.on_upload = fence_and_purge
    run_full_worker(job_id)

    assert _previews(env, job_id) == []
    assert status(env, job_id)["source_available"] is False


def test_a_fenced_worker_discards_its_preview_even_without_purge(env):
    job_id = _post(env, "/images/analyze/full", None).json()["job_id"]

    def fence(name):
        if "/preview/" in name:
            env.storage.on_upload = None
            with env.Session() as db:
                db.get(ImageAnalysisRun, job_id).fence += 1
                db.commit()

    env.storage.on_upload = fence
    run_full_worker(job_id)

    assert _previews(env, job_id) == []


def test_an_unreferenced_preview_counts_as_an_original_and_delete_removes_it(env):
    job_id = _post(env, "/images/analyze/full", None).json()["job_id"]
    run_full_worker(job_id)
    assert env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 200
    with env.Session() as db:  # reopen the case: a copy the row knows nothing about
        db.get(Job, job_id).source_deleted_at = None
        db.commit()
    env.storage.objects[f"images/{job_id}/preview/9-late.png"] = PNG

    assert status(env, job_id)["source_available"] is True
    assert env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 200
    assert _previews(env, job_id) == []
    assert status(env, job_id)["source_available"] is False


def test_the_rewritten_report_is_committed_before_the_old_one_is_deleted(env):
    job_id = _post(env, "/images/analyze/full", None).json()["job_id"]
    run_full_worker(job_id)
    old_report = job(env, job_id).minio_result_path
    env.storage.refuse_delete = lambda name: name == old_report

    failed = env.client.delete(f"/jobs/{job_id}/source", headers=jwt())

    assert failed.status_code == 503
    assert failed.json()["detail"]["code"] == "SOURCE_DELETE_FAILED"
    after = job(env, job_id)
    assert after.minio_result_path != old_report  # the new path was committed first
    assert after.minio_result_path in env.storage.objects
    assert after.source_deleted_at is None
    assert status(env, job_id)["source_available"] is True  # the old report is still listed

    env.storage.refuse_delete = None
    assert env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 200
    assert old_report not in env.storage.objects
    assert status(env, job_id)["source_available"] is False


def test_a_full_wait_true_read_survives_a_report_that_moved(env, monkeypatch):
    from workers import image_full_tasks

    armed = []

    def dispatch_and_run(job_id):
        run_full_worker(job_id)
        armed.append(True)  # from now on only the waiting route reads the report

    monkeypatch.setattr(image_full_tasks, "dispatch", dispatch_and_run)
    original = env.storage.download_file
    missed = []

    def flaky(bucket, name, file_path=None):
        if armed and "/reports/" in name and not missed:
            missed.append(name)
            raise KeyError(name)  # deleted between reading the path and the download
        return original(bucket, name, file_path)

    monkeypatch.setattr(env.storage, "download_file", flaky)
    body = {"mode": "full", "wait": True, "image_base64": PNG_B64, "filename": "foto.png",
            "project_id": env.project.id}
    r = env.client.post("/images/analyze", headers={**jwt(), "Idempotency-Key": "moved"}, json=body)

    assert r.status_code == 200, r.text
    assert missed and r.json()["status"] == "completed", r.json()["image"].get("reason_code")


def test_a_delete_between_the_terminal_commit_and_the_cache_write_is_not_undone(env, monkeypatch):
    job_id = _post(env, "/images/analyze/full", None).json()["job_id"]
    write = env.redis.set_job_result
    deleted = []

    def delete_first(target, payload):
        if target == job_id and not deleted:
            deleted.append(env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code)
        return write(target, payload)

    monkeypatch.setattr(env.redis, "set_job_result", delete_first)
    run_full_worker(job_id)

    assert deleted == [200]
    assert env.redis.get_job_result(job_id)["image"]["image_base64"] is None
    assert status(env, job_id)["source_available"] is False


def test_a_native_result_only_in_redis_is_reported_and_deleted(env):
    job_id = _post(env, "/images/ocr", None).json()["job_id"]
    with env.Session() as db:  # the MinIO write failed: only the cache has the result
        db.get(Job, job_id).minio_result_path = None
        db.commit()
    assert env.redis.get_job_result(job_id)["image"]["image_base64"]

    assert status(env, job_id)["source_available"] is True
    assert env.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 200
    assert env.redis.get_job_result(job_id)["image"]["image_base64"] is None
    assert status(env, job_id)["source_available"] is False


def test_a_failed_purge_is_retried_by_the_periodic_sweep(env):
    from workers.image_full_tasks import retry_image_purges

    job_id = _post(env, "/images/analyze/full", True).json()["job_id"]
    env.storage.refuse_delete = lambda name: True  # storage down when the job settles
    run_full_worker(job_id)

    settled = job(env, job_id)
    assert settled.status == JobStatus.COMPLETED  # a failed purge never fails the job
    assert settled.source_deleted_at is None
    assert f"images/{job_id}/source" in env.storage.objects
    assert status(env, job_id)["source_available"] is True

    assert retry_image_purges(force=True) == 0  # still down: kept, retried later
    env.storage.refuse_delete = None
    assert retry_image_purges(force=True) == 1

    assert job(env, job_id).source_deleted_at is not None
    assert f"images/{job_id}/source" not in env.storage.objects
    assert _previews(env, job_id) == []
    assert retry_image_purges(force=True) == 0  # idempotent: nothing left to do


def test_the_purge_retry_is_bounded(env):
    from shared.job_source import retry_pending_image_purges

    env.storage.refuse_delete = lambda name: True
    ids = [_post(env, "/images/analyze/full", True).json()["job_id"] for _ in range(3)]
    for job_id in ids:
        run_full_worker(job_id)
    env.storage.refuse_delete = None

    assert retry_pending_image_purges(env.Session, lambda: env.storage, limit=2) == 2
    assert sum(job(env, i).source_deleted_at is None for i in ids) == 1


def test_purge_source_descriptions_match_each_route_family():
    from api.main import app

    schema = app.openapi()

    def description(path):
        body = schema["paths"][path]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
        name = body["$ref"].rsplit("/", 1)[-1]
        return schema["components"]["schemas"][name]["properties"]["purge_source"]["description"]

    assert "ecoa `image_base64`" in description("/images/describe/upload")
    assert "ecoa `image_base64`" in description("/images/ocr/upload")
    analyze = description("/images/analyze/upload")
    assert "mode=single com wait=true" in analyze and "Idempotency-Key" in analyze
    faces = description("/images/faces/upload")
    assert "ecoa" not in faces and "`image.image_base64` null" in faces
