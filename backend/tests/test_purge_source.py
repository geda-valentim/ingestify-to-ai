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


# ---------------------------------------------------------------------------
# Review fixes: split exhaustion, idempotent split pages, monitoring writes,
# purge vs page retry locking, bookkeeping out of the requested configuration,
# recount under lock, unscheduled retries, admin bulk retry
# ---------------------------------------------------------------------------

from sqlalchemy.exc import IntegrityError  # noqa: E402

from shared import job_source  # noqa: E402
from shared.engines import dispatch as engine_dispatch  # noqa: E402
from shared.engines.ledger import recount_parent_pages  # noqa: E402
from shared.job_configuration import job_configuration  # noqa: E402


class FakeSplitter:
    """PDFSplitter stand-in: `pages` page files in the work dir."""
    pages = 2

    def __init__(self, temp_dir):
        self.temp_dir = temp_dir

    def split_pdf(self, path, job_id):
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        out = []
        for n in range(1, self.pages + 1):
            f = self.temp_dir / f"page_{n:04d}.pdf"
            f.write_bytes(b"%PDF")
            out.append((n, f, f"pages/{job_id}/page_{n:04d}.pdf"))
        return out


@pytest.fixture
def splitting(worker, monkeypatch, fake_redis):
    monkeypatch.setattr(tasks, "PDFSplitter", FakeSplitter)
    monkeypatch.setattr(tasks, "_page_route", lambda: None)
    queued = []
    monkeypatch.setattr(tasks.convert_page_task, "delay", lambda **kw: queued.append(kw))
    fake_redis.set_job_status(job_id=JOB_ID, job_type="main", status="processing")

    def split(retries=0):
        return run_as_attempt(tasks.split_pdf_task, lambda: tasks.split_pdf_task.run(
            split_job_id="split-1", parent_job_id=JOB_ID, file_path=str(worker.tmp / "livro.pdf")),
            retries=retries, monkeypatch=monkeypatch)
    return SimpleNamespace(split=split, queued=queued)


def test_split_exhausted_fails_the_main_job_and_purges(worker, splitting, monkeypatch, fake_redis):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf")

    class Broken(FakeSplitter):
        def split_pdf(self, path, job_id):
            raise ValueError("corrupt xref")
    monkeypatch.setattr(tasks, "PDFSplitter", Broken)

    with pytest.raises(_Retry):  # a retry ahead: the MAIN job stays open
        splitting.split(retries=0)
    assert worker.job().status == JobStatus.PROCESSING
    assert worker.minio.deleted == []

    with pytest.raises(_Retry):  # the last attempt: settled for good
        splitting.split(retries=tasks.split_pdf_task.max_retries)
    job = worker.job()
    assert job.status == JobStatus.FAILED and job.completed_at is not None
    assert "dividir o PDF" in job.error_message and "corrupt xref" in job.error_message
    assert fake_redis.get_job_status(JOB_ID)["status"] == "failed"
    assert worker.minio.deleted == [("ingestify-uploads", PDF_PATH)]
    # no longer 409 forever: the source is gone, the job is settled
    with worker.Session() as db:
        assert job_source.has_pending_work(db, db.get(Job, JOB_ID)) is False


def test_split_retry_reuses_the_page_rows(worker, splitting, monkeypatch):
    add_job(worker.Session, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf")
    calls = []

    def flaky(**kw):
        calls.append(kw)
        if len(calls) == 2:
            raise ConnectionError("broker down")  # page 2's dispatch fails
        splitting.queued.append(kw)
    monkeypatch.setattr(tasks.convert_page_task, "delay", flaky)

    with pytest.raises(_Retry):
        splitting.split(retries=0)
    with worker.Session() as db:  # page 1 started meanwhile
        db.query(Page).filter(Page.page_number == 1).one().status = JobStatus.PROCESSING
        db.commit()
        first_ids = {p.page_number: p.page_job_id for p in db.query(Page).filter(Page.job_id == JOB_ID)}

    splitting.split(retries=1)

    with worker.Session() as db:
        rows = db.query(Page).filter(Page.job_id == JOB_ID).order_by(Page.page_number).all()
        assert [(p.page_number, p.page_job_id) for p in rows] == sorted(first_ids.items())
    # page 1 is not run twice; page 2 is queued again under its own page job id
    assert [(kw["page_number"], kw["page_job_id"]) for kw in splitting.queued] == [
        (1, first_ids[1]), (2, first_ids[2])]


def test_one_page_row_per_job_and_page_number(Session):
    add_job(Session, pages={1: JobStatus.PENDING})
    with Session() as db:
        db.add(Page(job_id=JOB_ID, page_number=1, page_job_id="dup", status=JobStatus.PENDING))
        with pytest.raises(IntegrityError):
            db.commit()


def test_migration_cleanup_keeps_the_completed_row(Session):
    """shared.database.duplicate_page_rows: what the alembic migration deletes."""
    from shared.database import duplicate_page_rows
    from sqlalchemy import create_engine as ce, text
    engine = ce("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE pages (id TEXT, job_id TEXT, page_number INT, status TEXT, "
                          "updated_at TEXT)"))
        conn.execute(text("INSERT INTO pages VALUES ('a','j',1,'COMPLETED','2026-01-01'),"
                          "('b','j',1,'PENDING','2026-02-01'),('c','j',2,'PENDING','2026-01-01'),"
                          "('d','j',3,'FAILED','2026-01-01'),('e','j',3,'PENDING','2026-03-01')"))
        assert sorted(duplicate_page_rows(conn)) == ["b", "d"]


# --- monitoring ------------------------------------------------------------

@pytest.fixture
def monitor(worker, fake_redis, monkeypatch):
    from shared import minio_client
    from workers import monitoring
    monkeypatch.setattr(monitoring, "SessionLocal", worker.Session)
    monkeypatch.setattr(monitoring, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(minio_client, "get_minio_client", lambda: worker.minio)
    monkeypatch.setattr(monitoring.settings, "monitoring_enabled", True)
    monkeypatch.setattr(monitoring.settings, "monitoring_auto_retry_enabled", True)
    monkeypatch.setattr(monitoring.settings, "temp_storage_path", str(worker.tmp))
    submitted = []
    monkeypatch.setattr(engine_dispatch, "submit", lambda **kw: submitted.append(kw))

    def detached(model, **filters):
        with worker.Session() as db:  # rows of a closed session, as shared.queries returns them
            return db.query(model).filter_by(**filters).all()
    return SimpleNamespace(m=monitoring, detached=detached, submitted=submitted)


def test_detect_stuck_job_writes_the_database_and_purges(worker, monitor, monkeypatch):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING)
    monkeypatch.setattr(monitor.m, "get_stuck_jobs", lambda **kw: monitor.detached(Job, id=JOB_ID))
    monkeypatch.setattr(monitor.m, "get_stuck_pages", lambda **kw: [])

    assert monitor.m.detect_stuck_jobs()["stuck_jobs_detected"] == 1

    job = worker.job()
    assert job.status == JobStatus.FAILED and "stuck" in job.error_message
    assert worker.minio.deleted == [("ingestify-uploads", UPLOAD_PATH)]


def test_detect_stuck_page_settles_the_parent_and_purges(worker, monitor, monkeypatch):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.PROCESSING})
    monkeypatch.setattr(monitor.m, "get_stuck_jobs", lambda **kw: [])
    monkeypatch.setattr(monitor.m, "get_stuck_pages",
                        lambda **kw: monitor.detached(Page, job_id=JOB_ID, page_number=2))

    assert monitor.m.detect_stuck_jobs()["stuck_pages_detected"] == 1

    assert page_status(worker.Session, 2) == JobStatus.FAILED
    job = worker.job()
    assert job.status == JobStatus.PARTIAL and (job.pages_completed, job.pages_failed) == (1, 1)
    assert ("ingestify-pages", f"pages/{JOB_ID}/") in worker.minio.deleted


def test_auto_retry_requeues_failed_pages_through_the_retry_path(worker, monitor, monkeypatch):
    add_job(worker.Session, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})
    monkeypatch.setattr(monitor.m, "get_failed_pages_for_retry",
                        lambda **kw: monitor.detached(Page, job_id=JOB_ID, status=JobStatus.FAILED))

    assert monitor.m.auto_retry_failed_pages()["pages_retried"] == 1

    with worker.Session() as db:
        page = db.query(Page).filter(Page.job_id == JOB_ID, Page.page_number == 2).one()
        assert (page.status, page.retry_count) == (JobStatus.PENDING, 1)
        assert db.get(Job, JOB_ID).status == JobStatus.PROCESSING
    assert [kw["subject_id"] for kw in monitor.submitted] == [page.page_job_id]


def test_auto_retry_skips_a_job_whose_source_was_purged(worker, monitor, monkeypatch):
    add_job(worker.Session, status=JobStatus.PARTIAL, path=None, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})
    monkeypatch.setattr(monitor.m, "get_failed_pages_for_retry",
                        lambda **kw: monitor.detached(Page, job_id=JOB_ID, status=JobStatus.FAILED))

    assert monitor.m.auto_retry_failed_pages()["pages_retried"] == 0
    assert page_status(worker.Session, 2) == JobStatus.FAILED
    assert worker.job().status == JobStatus.PARTIAL and monitor.submitted == []


# --- purge vs page retry ---------------------------------------------------

def test_worker_purge_rechecks_under_the_lock(worker, monkeypatch):
    """A page retry commits its page PENDING just before the hook takes the lock."""
    add_job(worker.Session, purge=True, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})
    real_lock = job_source.lock_job

    def retry_wins(db, job_id):
        with worker.Session() as other:
            other.query(Page).filter(Page.page_number == 2).one().status = JobStatus.PENDING
            other.get(Job, job_id).status = JobStatus.PROCESSING
            other.commit()
        return real_lock(db, job_id)
    monkeypatch.setattr(job_source, "lock_job", retry_wins)

    tasks._purge_source_if_requested(JOB_ID)

    assert worker.minio.deleted == []
    assert worker.job().minio_upload_path == PDF_PATH


def test_delete_source_deletes_everything_before_its_single_commit(Session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "temp_storage_path", str(tmp_path))
    add_job(Session, status=JobStatus.COMPLETED, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED})
    copy = local_copy(tmp_path, name="livro.pdf")
    minio = FakeMinio()
    commits = []
    with Session() as db:
        job = job_source.lock_job(db, JOB_ID)
        real_commit = db.commit

        def commit():
            # the lock is released here: every file must already be gone
            commits.append((copy.exists(), list(minio.deleted)))
            real_commit()
        monkeypatch.setattr(db, "commit", commit)

        assert job_source.delete_source(db, job, lambda: minio) is True

    assert commits == [(False, [("ingestify-uploads", PDF_PATH), ("ingestify-pages", f"pages/{JOB_ID}/")])]


def test_delete_source_refuses_when_a_page_retry_committed_first(api, monkeypatch):
    add_job(api.Session, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})
    real_lock = routes.lock_job

    def retry_wins(db, job_id):
        with api.Session() as other:
            other.query(Page).filter(Page.page_number == 2).one().status = JobStatus.PENDING
            other.commit()
        return real_lock(db, job_id)
    monkeypatch.setattr(routes, "lock_job", retry_wins)

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 409 and r.json()["detail"]["code"] == "JOB_STILL_PROCESSING"
    assert api.minio.deleted == []


def test_page_retry_after_a_purge_won_the_lock_is_409(api, retry_enqueued, monkeypatch):
    add_job(api.Session, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})
    real_lock = routes.lock_job

    def purge_wins(db, job_id):
        with api.Session() as other:
            job_source.delete_source(other, other.get(Job, job_id), lambda: api.minio)
        return real_lock(db, job_id)
    monkeypatch.setattr(routes, "lock_job", purge_wins)

    r = api.client.post(f"/jobs/{JOB_ID}/pages/2/retry", headers=jwt())

    assert r.status_code == 409 and r.json()["detail"]["code"] == "SOURCE_NOT_AVAILABLE"
    assert retry_enqueued == []
    assert not (api.tmp / "uploads" / JOB_ID).exists()  # nothing restored for a retry that never runs
    api.db.expire_all()
    assert api.db.query(Page).filter(Page.page_number == 2).one().status == JobStatus.FAILED


def test_duplicate_purge_decides_under_the_lock(api, monkeypatch):
    add_duplicate(api, status=JobStatus.COMPLETED, pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})
    real_lock = job_source.lock_job

    def retry_wins(db, job_id):
        with api.Session() as other:
            other.query(Page).filter(Page.page_number == 2).one().status = JobStatus.PENDING
            other.commit()
        return real_lock(db, job_id)
    monkeypatch.setattr(job_source, "lock_job", retry_wins)

    body = post_file(api, "/upload", purge=True).json()

    assert body["duplicate"] is True and body["source_available"] is True
    assert api.minio.deleted == []
    api.db.expire_all()
    assert purge_requested(api.db.get(Job, JOB_ID)) is True


# --- bookkeeping is not the requested configuration ------------------------

def test_bookkeeping_stays_out_of_the_requested_configuration(api):
    r = api.client.post("/upload", headers=jwt(), data={"project_id": api.project.id, "purge_source": "true"},
                        files={"file": ("relatorio.docx", CONTENT, "application/octet-stream")})
    job_id = r.json()["job_id"]
    with api.Session() as db:
        job = db.get(Job, job_id)
        assert job.operation_key and job.purge_source is True
        job.status = JobStatus.COMPLETED
        db.commit()

    assert api.client.delete(f"/jobs/{job_id}/source", headers=jwt()).status_code == 200

    status = api.client.get(f"/jobs/{job_id}", headers=jwt()).json()
    assert status["configuration"]["options"] == {"purge_source": True}  # what was requested
    assert status["source_deleted_at"] and status["source_available"] is False
    assert configuration_of(api, job_id).options == {"purge_source": True}


def test_a_conversion_without_options_has_no_configuration(api):
    r = api.client.post("/upload", headers=jwt(), data={"project_id": api.project.id},
                        files={"file": ("relatorio.docx", CONTENT, "application/octet-stream")})
    assert configuration_of(api, r.json()["job_id"]) is None


def test_deleting_an_image_source_never_touches_its_configuration(api):
    add_job(api.Session, status=JobStatus.COMPLETED, source_type="image", filename="foto.png",
            path=f"uploads/{JOB_ID}/foto.png")
    with api.Session() as db:
        from shared.job_configuration import save_configuration
        save_configuration(db, db.get(Job, JOB_ID), operation="describe", options={"mode": "caption"})
        db.commit()

    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 200

    api.db.expire_all()
    job = api.db.get(Job, JOB_ID)
    assert job_configuration(job)["options"] == {"mode": "caption"}
    assert source_deleted_at(job) is not None


def test_a_duplicate_purge_request_does_not_rewrite_the_configuration(api):
    add_duplicate(api, status=JobStatus.PROCESSING)

    post_file(api, "/upload", purge=True)

    api.db.expire_all()
    job = api.db.get(Job, JOB_ID)
    assert purge_requested(job) is True
    assert job.configuration_row is None


# --- recount ---------------------------------------------------------------

def test_recount_reads_the_parent_under_lock_and_fresh_counts(Session, monkeypatch):
    add_job(Session, status=JobStatus.PROCESSING, pages={1: JobStatus.PROCESSING, 2: JobStatus.PROCESSING})
    locked = []
    real = type(Session().query(Job)).with_for_update

    def spy(self, *a, **kw):
        locked.append(self.column_descriptions[0]["name"])
        return real(self, *a, **kw)
    monkeypatch.setattr(type(Session().query(Job)), "with_for_update", spy)

    with Session() as stale:
        stale.get(Job, JOB_ID).pages_completed  # an older view of the parent in this session
        with Session() as other:  # the other page settles in another worker
            for page in other.query(Page).filter(Page.job_id == JOB_ID):
                page.status = JobStatus.COMPLETED
            other.commit()
        recount_parent_pages(stale, JOB_ID)
        stale.commit()

    assert locked[:2] == ["Job", "status"]
    with Session() as db:
        assert db.get(Job, JOB_ID).pages_completed == 2


# --- a retry that cannot be scheduled --------------------------------------

def test_unscheduled_retry_fails_the_main_job_and_purges(worker, monkeypatch, fake_redis):
    add_job(worker.Session, purge=True)
    worker.converter.convert_to_markdown.side_effect = RuntimeError("docling exploded")

    def publish_fails(*a, **kw):
        raise ConnectionError("broker down")
    monkeypatch.setattr(tasks.process_conversion, "retry", publish_fails)
    tasks.process_conversion.push_request(id="celery-task-id", retries=0, called_directly=False)
    try:
        with pytest.raises(ConnectionError):
            worker.convert()
    finally:
        tasks.process_conversion.pop_request()

    job = worker.job()
    assert job.status == JobStatus.FAILED and job.completed_at is not None
    assert "não pôde ser agendada" in job.error_message
    assert fake_redis.get_job_status(JOB_ID)["status"] == "failed"
    assert worker.minio.deleted == [("ingestify-uploads", UPLOAD_PATH)]


def test_unscheduled_page_retry_fails_the_page(worker, monkeypatch):
    add_job(worker.Session, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.PROCESSING})

    class Task:
        name = "workers.tasks.convert_page_task"

        def retry(self, **kw):
            raise ConnectionError("broker down")

    with pytest.raises(ConnectionError):
        raise tasks._retry_or_settle(Task(), exc=RuntimeError("boom"), countdown=1, settle=lambda error:
                                     tasks._mark_page_failed("[test]", "page-2", JOB_ID, 2, error))

    assert page_status(worker.Session, 2) == JobStatus.FAILED
    assert worker.job().status == JobStatus.PARTIAL


# --- POST /admin/jobs/{id}/retry-all-failed ---------------------------------

@pytest.fixture
def admin_retry(api, fake_redis, monkeypatch):
    import asyncio
    from api import admin_routes
    from shared import minio_client
    submitted = []
    monkeypatch.setattr(engine_dispatch, "submit", lambda **kw: submitted.append(kw))
    monkeypatch.setattr(admin_routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(minio_client, "get_minio_client", lambda: api.minio)
    monkeypatch.setattr(admin_routes.settings, "temp_storage_path", str(api.tmp))

    def call():
        return asyncio.run(admin_routes.retry_all_failed_pages(
            JOB_ID, admin_user=SimpleNamespace(email="op@example.com"), db=api.db))
    return SimpleNamespace(call=call, submitted=submitted)


def test_admin_retry_all_failed_enqueues_every_failed_page(api, admin_retry):
    add_job(api.Session, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.FAILED, 2: JobStatus.COMPLETED, 3: JobStatus.FAILED})

    body = admin_retry.call()

    assert body["pages_retried"] == 2 and body["errors"] is None
    api.db.expire_all()
    pages = {p.page_number: p for p in api.db.query(Page).filter(Page.job_id == JOB_ID)}
    assert [(pages[n].status, pages[n].retry_count) for n in (1, 3)] == [(JobStatus.PENDING, 1)] * 2
    assert api.db.get(Job, JOB_ID).status == JobStatus.PROCESSING
    assert sorted(kw["subject_id"] for kw in admin_retry.submitted) == sorted(
        [pages[1].page_job_id, pages[3].page_job_id])
    assert body["page_job_ids"] == {1: pages[1].page_job_id, 3: pages[3].page_job_id}


def test_admin_retry_all_failed_without_a_source_is_409_and_changes_nothing(api, admin_retry):
    from fastapi import HTTPException
    add_job(api.Session, status=JobStatus.PARTIAL, path=None, filename="livro.pdf",
            pages={1: JobStatus.FAILED, 2: JobStatus.COMPLETED})
    with api.Session() as db:
        db.query(Page).update({Page.minio_page_path: None})
        db.commit()

    with pytest.raises(HTTPException) as e:
        admin_retry.call()

    assert e.value.status_code == 409 and e.value.detail["code"] == "SOURCE_NOT_AVAILABLE"
    api.db.expire_all()
    page = api.db.query(Page).filter(Page.page_number == 1).one()
    assert (page.status, page.retry_count) == (JobStatus.FAILED, 0)
    assert api.db.get(Job, JOB_ID).status == JobStatus.PARTIAL
    assert admin_retry.submitted == []
