"""
"Keep or delete the source files" of a document conversion.

- `purge_source=true` on POST /upload and POST /convert is stored with the job
  (a JobConfiguration row), not only in the Celery message;
- the workers delete the source files (original + split per-page PDFs, MinIO and
  local) when the MAIN job settles for good: COMPLETED, or FAILED / PARTIAL after
  its last automatic retry, never while a retry or a page is still pending;
- a failed attempt with a Celery retry ahead waits as PENDING (page: PENDING), and
  the MAIN job becomes PARTIAL once every page settled with some failed;
- a purge that fails never fails the job;
- DELETE /jobs/{job_id}/source deletes them on request (documents and audio), 409
  while anything is pending; GET /jobs/{job_id} reports `source_available`,
  `source_deleted_at`, `source_deletable`; page PDFs answer 410 SOURCE_PURGED;
- dedup honours purge_source; page retry without a source is a clean 409.

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
from shared.job_source import purge_requested, save_purge_option, source_available, source_deleted_at
from shared.models import Job, JobConfiguration, JobStatus, Page, Project, User
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

    def delete_folder(self, bucket_name, folder_prefix):
        if self.fail:
            raise ConnectionError("minio down")
        self.deleted.append((bucket_name, folder_prefix))
        return True

    def download_file(self, bucket_name, object_name, file_path=None):
        if self.fail:
            raise ConnectionError("minio down")
        from pathlib import Path
        Path(file_path).write_bytes(b"%PDF-1.4 restored")
        return True

    def file_exists(self, bucket_name, object_name):
        return True

    def get_presigned_url(self, *args, **kwargs):
        return "http://minio/signed"


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
            source_type="file", user_id=ALICE, filename="relatorio.docx", pages=None, checksum=None,
            project_id=None):
    """`pages`: {page_number: JobStatus} creates split Page rows (with page PDFs in MinIO)."""
    with Session() as db:
        job = Job(id=job_id, user_id=user_id, filename=filename, name=filename, job_type="MAIN",
                  source_type=source_type, status=status, minio_upload_path=path,
                  file_checksum=checksum, project_id=project_id,
                  total_pages=len(pages) if pages else None,
                  created_at=datetime(2026, 10, 1, 8, 0, 0))
        db.add(job)
        for number, page_status in (pages or {}).items():
            db.add(Page(job_id=job_id, page_number=number, page_job_id=f"page-{number}",
                        status=page_status, minio_page_path=f"pages/{job_id}/page_{number:04d}.pdf"))
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
            job = db.get(Job, JOB_ID)
            job.configuration_row, job.pages  # loaded before the session closes
            return job

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


class _Retry(Exception):
    """Stands in for celery.exceptions.Retry: the attempt ends, Celery runs the next one."""


def run_as_attempt(task, call, retries=0, monkeypatch=None):
    """Run a task body as a worker would (a real request, `retries` done so far)."""
    monkeypatch.setattr(task, "retry", lambda *a, **kw: _Retry())
    task.push_request(id="celery-task-id", retries=retries, called_directly=False)
    try:
        return call()
    finally:
        task.pop_request()


def test_failed_attempt_with_a_retry_ahead_waits_pending_and_keeps_the_files(worker, monkeypatch, fake_redis):
    add_job(worker.Session, purge=True)
    worker.converter.convert_to_markdown.side_effect = RuntimeError("docling exploded")

    with pytest.raises(_Retry):
        run_as_attempt(tasks.process_conversion, worker.convert, retries=0, monkeypatch=monkeypatch)

    job = worker.job()
    # Durable marker that work is still due: PENDING (queued), not FAILED
    assert job.status == JobStatus.PENDING
    assert job.error_message == "docling exploded" and job.completed_at is None
    assert fake_redis.get_job_status(JOB_ID)["status"] == "queued"
    assert worker.minio.deleted == []
    assert job.minio_upload_path == UPLOAD_PATH
    assert (worker.tmp / "uploads" / JOB_ID / "relatorio.docx").exists()


def test_last_failed_attempt_fails_the_job_and_then_purges(worker, monkeypatch):
    add_job(worker.Session, purge=True)
    worker.converter.convert_to_markdown.side_effect = RuntimeError("docling exploded")

    with pytest.raises(_Retry):
        run_as_attempt(tasks.process_conversion, worker.convert,
                       retries=tasks.process_conversion.max_retries, monkeypatch=monkeypatch)

    job = worker.job()
    assert job.status == JobStatus.FAILED
    assert worker.minio.deleted == [("ingestify-uploads", UPLOAD_PATH)]
    assert job.minio_upload_path is None
    assert source_deleted_at(job) is not None
    assert not (worker.tmp / "uploads" / JOB_ID).exists()


def test_failed_job_without_purge_keeps_the_original(worker):
    add_job(worker.Session)
    worker.converter.convert_to_markdown.side_effect = RuntimeError("docling exploded")

    with pytest.raises(Exception):
        worker.convert()  # a direct call: no retry ahead, settles FAILED

    job = worker.job()
    assert job.status == JobStatus.FAILED
    assert worker.minio.deleted == []
    assert job.minio_upload_path == UPLOAD_PATH
    assert source_deleted_at(job) is None


def test_purge_failure_does_not_fail_the_job(worker):
    add_job(worker.Session, purge=True)
    worker.minio.fail = True

    assert worker.convert()["status"] == "completed"

    job = worker.job()
    assert job.status == JobStatus.COMPLETED
    assert job.minio_upload_path == UPLOAD_PATH  # kept, still referenced


PDF_PATH = f"uploads/{JOB_ID}/livro.pdf"


def test_multipage_pdf_purge_deletes_the_original_and_the_page_pdfs(worker):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.COMPLETED})
    work_pages = worker.tmp / JOB_ID / "pages"
    work_pages.mkdir(parents=True)
    (work_pages / "page_0001.pdf").write_bytes(b"%PDF")

    worker.merge()

    job = worker.job()
    assert job.status == JobStatus.COMPLETED
    assert worker.minio.deleted == [("ingestify-uploads", PDF_PATH), ("ingestify-pages", f"pages/{JOB_ID}/")]
    assert job.minio_upload_path is None
    with worker.Session() as db:
        assert all(p.minio_page_path is None for p in db.query(Page).filter(Page.job_id == JOB_ID))
        # The results stay
        assert db.get(Job, JOB_ID).status == JobStatus.COMPLETED
    assert not (worker.tmp / JOB_ID).exists()
    assert source_available(worker.job()) is False
    assert source_deleted_at(worker.job()) is not None


def page_status(Session, number):
    with Session() as db:
        return db.query(Page).filter(Page.job_id == JOB_ID, Page.page_number == number).one().status


def test_a_page_with_a_retry_ahead_keeps_the_job_open(worker):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.PROCESSING})

    tasks._mark_page_failed("[test]", "page-2", JOB_ID, 2, "boom", retrying=True)

    assert page_status(worker.Session, 2) == JobStatus.PENDING
    assert worker.job().status == JobStatus.PROCESSING
    assert worker.minio.deleted == []


def test_all_pages_settled_with_failures_make_the_job_partial_and_purge(worker):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.PROCESSING, 3: JobStatus.COMPLETED})

    tasks._mark_page_failed("[test]", "page-2", JOB_ID, 2, "boom")

    job = worker.job()
    assert job.status == JobStatus.PARTIAL
    assert (job.pages_completed, job.pages_failed) == (2, 1)
    assert job.completed_at is not None
    assert "1 de 3 páginas falharam" in job.error_message
    # purge_source: settled for good (no retry left) -> source files deleted
    assert ("ingestify-uploads", PDF_PATH) in worker.minio.deleted
    assert ("ingestify-pages", f"pages/{JOB_ID}/") in worker.minio.deleted


def test_partial_job_without_purge_keeps_its_files(worker):
    add_job(worker.Session, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.PROCESSING})

    tasks._mark_page_failed("[test]", "page-2", JOB_ID, 2, "boom")

    assert worker.job().status == JobStatus.PARTIAL
    assert worker.minio.deleted == []


def test_job_not_settled_while_other_pages_run_or_split_is_incomplete(worker):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.PROCESSING, 2: JobStatus.PROCESSING})
    tasks._mark_page_failed("[test]", "page-2", JOB_ID, 2, "boom")
    assert worker.job().status == JobStatus.PROCESSING

    with worker.Session() as db:  # still splitting: 3 pages announced, 2 rows so far
        db.get(Job, JOB_ID).total_pages = 3
        db.query(Page).filter(Page.page_number == 1).one().status = JobStatus.COMPLETED
        db.commit()
    tasks._mark_page_failed("[test]", "page-2", JOB_ID, 2, "boom")
    assert worker.job().status == JobStatus.PROCESSING
    assert worker.minio.deleted == []


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
    assert row is not None and row.options["purge_source"] is True


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_purge_source_defaults_to_keeping_the_original(api, endpoint):
    data = {"project_id": api.project.id}
    if endpoint == "/convert":
        data["source_type"] = "file"
    r = api.client.post(endpoint, headers=jwt(), data=data,
                        files={"file": ("outro.docx", b"PK\x03\x04 other", "application/octet-stream")})

    assert r.status_code == 200, r.text
    row = configuration_of(api, r.json()["job_id"])
    assert row is None or "purge_source" not in row.options


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
    body = r.json()
    assert (body["job_id"], body["source_deleted"]) == (JOB_ID, True)
    assert body["source_deleted_at"]
    assert api.minio.deleted == [("ingestify-uploads", UPLOAD_PATH)]
    assert not copy.exists()
    api.db.expire_all()
    job = api.db.get(Job, JOB_ID)
    assert job.minio_upload_path is None and job.status == JobStatus.COMPLETED
    # Gone now: a second call is a 404, GET says so
    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 404
    status = api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()
    assert status["source_available"] is False
    assert status["source_deleted_at"] == body["source_deleted_at"].rstrip("Z")
    assert status["source_deletable"] is False


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


# ---------------------------------------------------------------------------
# Page PDFs, pending work (409), page retry, DELETE /jobs/{id}, URL downloads
# ---------------------------------------------------------------------------

@pytest.fixture
def retry_enqueued(api, monkeypatch):
    """The page retry's enqueue, without a broker or a document_conversion route."""
    calls = []
    monkeypatch.setattr(routes, "_engine_celery", lambda: None)
    monkeypatch.setattr(routes.engine_dispatch, "submit", lambda **kw: calls.append(kw))
    return calls


def test_delete_source_also_deletes_the_page_pdfs_and_page_pdf_answers_410(api):
    add_job(api.Session, status=JobStatus.COMPLETED, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.COMPLETED})
    assert api.client.get(f"/jobs/{JOB_ID}/pages/1/pdf", headers=jwt()).status_code == 200

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 200, r.text
    assert api.minio.deleted == [("ingestify-uploads", PDF_PATH), ("ingestify-pages", f"pages/{JOB_ID}/")]
    gone = api.client.get(f"/jobs/{JOB_ID}/pages/1/pdf", headers=jwt())
    assert gone.status_code == 410
    detail = gone.json()["detail"]
    assert detail["code"] == "SOURCE_PURGED"
    assert "apagados em" in detail["message"] and "UTC" in detail["message"]
    assert detail["source_deleted_at"]


def test_delete_source_is_409_while_a_page_is_pending(api):
    add_job(api.Session, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.PENDING})

    status = api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()
    assert status["source_available"] is True and status["source_deletable"] is False
    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "JOB_STILL_PROCESSING"
    assert api.minio.deleted == []


def test_get_job_reports_source_deletable_from_the_database(api, fake_redis):
    add_job(api.Session, status=JobStatus.PENDING)  # e.g. a Celery retry waiting
    fake_redis.set_job_status(job_id=JOB_ID, job_type="main", status="failed", error="boom")

    status = api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()

    assert status["source_available"] is True
    assert status["source_deletable"] is False
    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 409


def test_page_retry_without_a_source_is_409_and_changes_nothing(api, retry_enqueued):
    add_job(api.Session, status=JobStatus.PARTIAL, path=None, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})
    with api.Session() as db:  # the page PDFs went with the original
        for page in db.query(Page).filter(Page.job_id == JOB_ID):
            page.minio_page_path = None
        db.commit()

    r = api.client.post(f"/jobs/{JOB_ID}/pages/2/retry", headers=jwt())

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "SOURCE_NOT_AVAILABLE"
    assert "apagado" in r.json()["detail"]["message"]
    api.db.expire_all()
    page = api.db.query(Page).filter(Page.job_id == JOB_ID, Page.page_number == 2).one()
    assert (page.status, page.retry_count) == (JobStatus.FAILED, 0)
    assert api.db.get(Job, JOB_ID).status == JobStatus.PARTIAL
    assert retry_enqueued == []


def test_page_retry_reopens_the_job_and_blocks_delete_source(api, retry_enqueued):
    add_job(api.Session, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})

    r = api.client.post(f"/jobs/{JOB_ID}/pages/2/retry", headers=jwt())

    assert r.status_code == 200, r.text
    assert len(retry_enqueued) == 1
    # restored from MinIO into the upload dir, read by the retried page
    assert (api.tmp / "uploads" / JOB_ID / "livro.pdf").exists()
    api.db.expire_all()
    page = api.db.query(Page).filter(Page.job_id == JOB_ID, Page.page_number == 2).one()
    assert (page.status, page.retry_count) == (JobStatus.PENDING, 1)
    job = api.db.get(Job, JOB_ID)
    assert job.status == JobStatus.PROCESSING and job.completed_at is None
    # The race window: the original must not go while the retry is queued
    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 409
    assert api.minio.deleted == []


def test_page_retry_that_cannot_be_queued_puts_everything_back(api, monkeypatch):
    add_job(api.Session, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})
    monkeypatch.setattr(routes, "_engine_celery", lambda: None)

    def broken(**kw):
        raise ConnectionError("broker down")
    monkeypatch.setattr(routes.engine_dispatch, "submit", broken)

    r = api.client.post(f"/jobs/{JOB_ID}/pages/2/retry", headers=jwt())

    assert r.status_code == 500
    api.db.expire_all()
    page = api.db.query(Page).filter(Page.job_id == JOB_ID, Page.page_number == 2).one()
    assert (page.status, page.retry_count) == (JobStatus.FAILED, 0)
    assert api.db.get(Job, JOB_ID).status == JobStatus.PARTIAL


def test_delete_job_deletes_a_document_original_from_the_uploads_bucket(api, monkeypatch):
    add_job(api.Session, status=JobStatus.COMPLETED)
    monkeypatch.setattr(routes, "get_es_client", lambda: (_ for _ in ()).throw(RuntimeError("no es")))

    r = api.client.delete(f"/jobs/{JOB_ID}", headers=jwt())

    assert r.status_code == 200, r.text
    assert ("ingestify-uploads", UPLOAD_PATH) in api.minio.deleted
    assert all(bucket != "ingestify-audio" for bucket, _ in api.minio.deleted)


def test_url_download_in_the_work_dir_counts_as_the_source(api):
    add_job(api.Session, status=JobStatus.FAILED, path=None, source_type="url", filename="doc.pdf")
    work = api.tmp / JOB_ID
    work.mkdir()
    (work / "doc.pdf").write_bytes(b"%PDF")

    assert api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()["source_available"] is True
    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 200
    assert not work.exists()


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------

CONTENT = b"PK\x03\x04 dedup document"


def post_file(api, endpoint, purge):
    import hashlib
    data = {"project_id": api.project.id, "purge_source": "true" if purge else "false"}
    if endpoint == "/convert":
        data["source_type"] = "file"
    return api.client.post(endpoint, headers=jwt(), data=data,
                           files={"file": ("relatorio.docx", CONTENT, "application/octet-stream")})


def add_duplicate(api, **kw):
    import hashlib
    add_job(api.Session, checksum=hashlib.sha256(CONTENT).hexdigest(), project_id=api.project.id, **kw)


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_duplicate_with_purge_of_a_completed_job_purges_it_now(api, endpoint):
    add_duplicate(api, status=JobStatus.COMPLETED)

    r = post_file(api, endpoint, purge=True)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_id"] == JOB_ID and body["duplicate"] is True
    assert body["source_available"] is False
    assert "apagado" in body["message"]
    assert api.minio.deleted == [("ingestify-uploads", UPLOAD_PATH)]
    api.db.expire_all()
    assert purge_requested(api.db.get(Job, JOB_ID)) is True
    assert api.enqueued == []


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_duplicate_with_purge_of_a_running_job_records_the_option(api, endpoint):
    add_duplicate(api, status=JobStatus.PROCESSING)

    body = post_file(api, endpoint, purge=True).json()

    assert body["duplicate"] is True and body["source_available"] is True
    assert "será apagado" in body["message"]
    assert api.minio.deleted == []
    api.db.expire_all()
    assert purge_requested(api.db.get(Job, JOB_ID)) is True


def test_duplicate_purge_failure_never_fails_the_request(api):
    add_duplicate(api, status=JobStatus.COMPLETED)
    api.minio.fail = True

    r = post_file(api, "/upload", purge=True)

    assert r.status_code == 200, r.text
    assert r.json()["duplicate"] is True and r.json()["source_available"] is True


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_keep_request_is_not_answered_by_a_purged_duplicate(api, endpoint):
    add_duplicate(api, status=JobStatus.COMPLETED, path=None)  # its original is gone

    r = post_file(api, endpoint, purge=False)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_id"] != JOB_ID and body["duplicate"] is False
    assert JOB_ID in body["message"]
    assert len(api.enqueued) == 1


def test_keep_request_is_not_answered_by_a_job_that_will_purge(api):
    add_duplicate(api, status=JobStatus.PROCESSING, purge=True)

    body = post_file(api, "/upload", purge=False).json()

    assert body["job_id"] != JOB_ID and body["duplicate"] is False


def test_keep_request_reuses_a_duplicate_that_kept_its_original(api):
    add_duplicate(api, status=JobStatus.COMPLETED)

    body = post_file(api, "/upload", purge=False).json()

    assert body["job_id"] == JOB_ID and body["duplicate"] is True and body["source_available"] is True
    assert api.minio.deleted == []


# ---------------------------------------------------------------------------
# Dedup per operation (P17) and per attempt (P14)
# ---------------------------------------------------------------------------

def post_upload(api, preset=None, content=CONTENT, name="relatorio.docx"):
    data = {"project_id": api.project.id}
    if preset:
        data["docling_preset"] = preset
    return api.client.post("/upload", headers=jwt(), data=data,
                           files={"file": (name, content, "application/octet-stream")}).json()


def test_same_file_same_operation_dedups_other_options_do_not(api):
    first = post_upload(api, preset="fast")
    assert post_upload(api, preset="fast")["job_id"] == first["job_id"]

    other = post_upload(api, preset="quality")
    assert other["job_id"] != first["job_id"] and other["duplicate"] is False
    assert post_upload(api, preset="quality")["job_id"] == other["job_id"]


def test_a_vision_job_of_the_same_bytes_is_never_a_duplicate(api):
    """describe / OCR / analyze of an image are other operations on the same bytes."""
    import hashlib
    image = b"\x89PNG\r\n\x1a\n same image"
    add_job(api.Session, status=JobStatus.COMPLETED, source_type="image", filename="foto.png", path=None,
            checksum=hashlib.sha256(image).hexdigest(), project_id=api.project.id)

    body = post_upload(api, content=image, name="foto.png")

    assert body["job_id"] != JOB_ID and body["duplicate"] is False


@pytest.mark.parametrize("settled", [JobStatus.FAILED, JobStatus.PARTIAL])
def test_a_terminally_failed_job_is_never_returned_the_resend_is_a_new_attempt(api, settled):
    add_duplicate(api, status=settled)

    body = post_file(api, "/upload", purge=False)

    assert body.status_code == 200
    assert body.json()["job_id"] != JOB_ID and body.json()["duplicate"] is False


def test_a_job_recorded_before_operation_keys_still_dedups(api):
    add_duplicate(api, status=JobStatus.COMPLETED)  # no operation_key stored

    assert post_upload(api, preset="quality")["job_id"] == JOB_ID
