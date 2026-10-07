"""
"Keep or delete the original file" for document conversion.

- `purge_source=true` on POST /upload and POST /convert is stored with the job
  (a JobConfiguration row), not only in the Celery message;
- the workers delete the original (MinIO object + local copy) when the MAIN job
  ends COMPLETED: single document, and multi-page PDF after the merge (also when
  the merge only happens after a page retry);
- failed / partial jobs keep it (page retry restores it from MinIO);
- a purge that fails never fails the job;
- DELETE /jobs/{job_id}/source deletes it on request (documents and audio);
- GET /jobs/{job_id} says whether it still exists (`source_available`).

SQLite with the real models, fakeredis through the real RedisClient, fake MinIO.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker)
from api import routes
from shared import projects as projects_module
from shared.auth import create_access_token
from shared.config import get_settings
from shared.database import Base, get_db
from shared.job_source import purge_requested, save_purge_option, source_available
from shared.models import Job, JobConfiguration, JobStatus, Project, User
from workers import tasks

ALICE = "user-alice"
BOB = "user-bob"
JOB_ID = "11111111-2222-4333-8444-555555555555"
UPLOAD_PATH = f"uploads/{JOB_ID}/relatorio.docx"


class FakeMinio:
    bucket_uploads = "ingestify-uploads"
    bucket_audio = "ingestify-audio"
    bucket_pages = "ingestify-pages"
    bucket_results = "ingestify-results"

    def __init__(self, fail=False):
        self.fail = fail
        self.deleted = []
        self.uploaded = []

    def upload_file(self, **kwargs):
        self.uploaded.append(kwargs)

    def delete_file(self, bucket_name, object_name):
        if self.fail:
            raise ConnectionError("minio down")
        self.deleted.append((bucket_name, object_name))
        return True


@pytest.fixture
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([
            User(id=ALICE, email="alice@example.com", username="alice", hashed_password="x"),
            User(id=BOB, email="bob@example.com", username="bob", hashed_password="x"),
        ])
        db.commit()
    return factory


def add_job(Session, *, purge=False, status=JobStatus.PENDING, path=UPLOAD_PATH, job_id=JOB_ID,
            source_type="file", user_id=ALICE, filename="relatorio.docx"):
    with Session() as db:
        job = Job(id=job_id, user_id=user_id, filename=filename, name=filename, job_type="MAIN",
                  source_type=source_type, status=status, minio_upload_path=path,
                  created_at=datetime(2026, 10, 1, 8, 0, 0))
        db.add(job)
        if purge:
            save_purge_option(db, job)
        db.commit()


def local_copy(tmp_path, job_id=JOB_ID, area="uploads", name="relatorio.docx"):
    directory = tmp_path / area / job_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"PK\x03\x04 document")
    return path


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

@pytest.fixture
def worker(Session, fake_redis, tmp_path, monkeypatch):
    minio = FakeMinio()
    es = MagicMock()
    es.store_job_result.return_value = True
    converter = MagicMock()
    converter.convert_to_markdown.return_value = {"markdown": "# Relatório", "metadata": {"pages": 1}}

    monkeypatch.setattr(tasks.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(get_settings(), "temp_storage_path", str(tmp_path))  # shared.job_source
    monkeypatch.setattr(tasks, "SessionLocal", Session)
    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(tasks, "get_es_client", lambda: es)
    monkeypatch.setattr(tasks, "get_minio_client", lambda: minio)
    monkeypatch.setattr(tasks, "get_converter", lambda *a, **kw: converter)
    monkeypatch.setattr(tasks, "should_split_pdf", lambda *a, **kw: False)

    def convert():
        source = local_copy(tmp_path)
        return tasks.process_conversion.run(job_id=JOB_ID, source_type="file", source=str(source),
                                            options={"docling_preset": "fast"})

    def merge():
        return tasks.merge_pages_task.run(merge_job_id="merge-1", parent_job_id=JOB_ID)

    def job():
        with Session() as db:
            return db.get(Job, JOB_ID)

    return SimpleNamespace(convert=convert, merge=merge, job=job, minio=minio, converter=converter,
                           tmp=tmp_path, Session=Session)


def test_purge_on_completed_single_document(worker):
    add_job(worker.Session, purge=True)

    assert worker.convert()["status"] == "completed"

    job = worker.job()
    assert job.status == JobStatus.COMPLETED
    assert worker.minio.deleted == [("ingestify-uploads", UPLOAD_PATH)]
    assert job.minio_upload_path is None
    assert not (worker.tmp / "uploads" / JOB_ID).exists()
    assert source_available(job) is False


def test_without_purge_the_original_is_kept(worker):
    add_job(worker.Session)

    worker.convert()

    assert worker.minio.deleted == []
    assert worker.job().minio_upload_path == UPLOAD_PATH
    assert source_available(worker.job()) is True


def test_failed_conversion_keeps_the_original(worker):
    add_job(worker.Session, purge=True)
    worker.converter.convert_to_markdown.side_effect = RuntimeError("docling exploded")

    with pytest.raises(Exception):
        worker.convert()

    job = worker.job()
    assert job.status == JobStatus.FAILED
    assert worker.minio.deleted == []
    assert job.minio_upload_path == UPLOAD_PATH
    assert (worker.tmp / "uploads" / JOB_ID / "relatorio.docx").exists()


def test_purge_failure_does_not_fail_the_job(worker):
    add_job(worker.Session, purge=True)
    worker.minio.fail = True

    assert worker.convert()["status"] == "completed"

    job = worker.job()
    assert job.status == JobStatus.COMPLETED
    assert job.minio_upload_path == UPLOAD_PATH  # kept, still referenced


def test_multipage_pdf_is_purged_after_the_merge(worker):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING,
            path=f"uploads/{JOB_ID}/livro.pdf", filename="livro.pdf")

    worker.merge()

    job = worker.job()
    assert job.status == JobStatus.COMPLETED
    assert worker.minio.deleted == [("ingestify-uploads", f"uploads/{JOB_ID}/livro.pdf")]
    assert job.minio_upload_path is None
    # Only the original goes: the split per-page PDFs live in their own bucket
    assert all(bucket == "ingestify-uploads" for bucket, _ in worker.minio.deleted)


def test_partial_job_keeps_the_original_until_a_retry_completes_it(worker, fake_redis):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING,
            path=f"uploads/{JOB_ID}/livro.pdf", filename="livro.pdf")

    # A page fails: the MAIN job is not completed, nothing is purged
    tasks._mark_page_failed("[test]", "page-2", JOB_ID, 2, "boom")
    tasks._purge_source_if_requested(JOB_ID)
    assert worker.minio.deleted == []
    assert worker.job().minio_upload_path == f"uploads/{JOB_ID}/livro.pdf"

    # The retry succeeds, the merge runs and completes the job: now it goes
    worker.merge()
    assert worker.job().status == JobStatus.COMPLETED
    assert worker.minio.deleted == [("ingestify-uploads", f"uploads/{JOB_ID}/livro.pdf")]
    assert worker.job().minio_upload_path is None


def test_the_option_is_durable_with_the_job(Session):
    add_job(Session, purge=True)
    with Session() as db:
        row = db.get(JobConfiguration, JOB_ID)
        assert row.options == {"purge_source": True}
        assert purge_requested(db.get(Job, JOB_ID)) is True


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture
def api(Session, fake_redis, tmp_path, monkeypatch):
    minio = FakeMinio()
    enqueued = []
    db = Session()
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(get_settings(), "temp_storage_path", str(tmp_path))  # shared.job_source
    monkeypatch.setattr(projects_module.get_settings(), "upload_fallback_project", "")
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(routes, "get_minio_client", lambda: minio)
    monkeypatch.setattr(tasks.process_conversion, "delay", lambda **kw: enqueued.append(kw))
    monkeypatch.setattr(tasks.process_conversion, "apply_async", lambda **kw: enqueued.append(kw))

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    project = Project(user_id=ALICE, name="Docs", name_key=projects_module.name_key("Docs"))
    db.add(project)
    db.commit()
    yield SimpleNamespace(client=TestClient(app), db=db, Session=Session, minio=minio, tmp=tmp_path,
                          enqueued=enqueued, project=project)
    db.close()


def jwt(user_id=ALICE):
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


def configuration_of(api, job_id):
    api.db.expire_all()
    return api.db.get(JobConfiguration, job_id)


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_file_upload_accepts_purge_source(api, endpoint):
    data = {"project_id": api.project.id, "purge_source": "true"}
    if endpoint == "/convert":
        data["source_type"] = "file"
    r = api.client.post(endpoint, headers=jwt(), data=data,
                        files={"file": ("relatorio.docx", b"PK\x03\x04 doc", "application/octet-stream")})

    assert r.status_code == 200, r.text
    row = configuration_of(api, r.json()["job_id"])
    assert row is not None and row.options == {"purge_source": True}


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_purge_source_defaults_to_keeping_the_original(api, endpoint):
    data = {"project_id": api.project.id}
    if endpoint == "/convert":
        data["source_type"] = "file"
    r = api.client.post(endpoint, headers=jwt(), data=data,
                        files={"file": ("outro.docx", b"PK\x03\x04 other", "application/octet-stream")})

    assert r.status_code == 200, r.text
    assert configuration_of(api, r.json()["job_id"]) is None


def test_url_conversion_accepts_purge_source(api):
    r = api.client.post("/convert", headers=jwt(), data={
        "project_id": api.project.id, "source_type": "url",
        "source": "https://example.com/doc.pdf", "purge_source": "true"})

    assert r.status_code == 200, r.text
    assert configuration_of(api, r.json()["job_id"]).options == {"purge_source": True}
    assert api.enqueued[-1]["source_type"] == "url"


def test_get_job_reports_source_available(api):
    add_job(api.Session, status=JobStatus.COMPLETED)
    assert api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()["source_available"] is True

    with api.Session() as db:
        db.get(Job, JOB_ID).minio_upload_path = None
        db.commit()
    api.db.expire_all()
    assert api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()["source_available"] is False


def test_delete_source_happy_path(api):
    add_job(api.Session, status=JobStatus.COMPLETED)
    copy = local_copy(api.tmp)

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 200, r.text
    assert r.json() == {"job_id": JOB_ID, "source_deleted": True}
    assert api.minio.deleted == [("ingestify-uploads", UPLOAD_PATH)]
    assert not copy.exists()
    api.db.expire_all()
    job = api.db.get(Job, JOB_ID)
    assert job.minio_upload_path is None and job.status == JobStatus.COMPLETED
    # Gone now: a second call is a 404, GET says so
    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 404
    assert api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()["source_available"] is False


def test_delete_source_of_a_failed_job_removes_the_local_copy(api):
    add_job(api.Session, status=JobStatus.FAILED, path=None)
    copy = local_copy(api.tmp)

    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 200
    assert not copy.exists()


def test_delete_source_of_an_audio_job_uses_the_audio_bucket(api):
    path = f"audio/{JOB_ID}/aula.mp3"
    add_job(api.Session, status=JobStatus.COMPLETED, path=path, source_type="audio", filename="aula.mp3")

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 200, r.text
    assert api.minio.deleted == [("ingestify-audio", path)]


def test_delete_source_of_someone_elses_job_is_404(api):
    add_job(api.Session, status=JobStatus.COMPLETED)

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt(BOB))

    assert r.status_code == 404
    assert api.minio.deleted == []


def test_delete_source_of_an_unknown_job_is_404(api):
    assert api.client.delete("/jobs/does-not-exist/source", headers=jwt()).status_code == 404


def test_delete_source_without_an_original_is_404(api):
    add_job(api.Session, status=JobStatus.COMPLETED, path=None)

    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 404


@pytest.mark.parametrize("status", [JobStatus.PENDING, JobStatus.PROCESSING])
def test_delete_source_while_processing_is_409(api, status):
    add_job(api.Session, status=status)

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "JOB_STILL_PROCESSING"
    assert "processamento" in detail["message"]
    assert api.minio.deleted == []


def test_delete_source_when_storage_fails_keeps_the_reference(api):
    add_job(api.Session, status=JobStatus.COMPLETED)
    api.minio.fail = True

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "SOURCE_DELETE_FAILED"
    api.db.expire_all()
    assert api.db.get(Job, JOB_ID).minio_upload_path == UPLOAD_PATH
