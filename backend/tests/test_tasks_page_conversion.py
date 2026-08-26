"""
Characterization tests for the page-conversion Celery tasks.

Two tasks used to do the same job: `convert_page_task` (fed a pre-split page
file by `split_pdf_task`) and `process_page` (fed the whole PDF by the manual
retry endpoint, extracting the page itself). `process_page` was broken:
`PDFSplitter.extract_single_page` returns `Tuple[Path, Optional[str]]` and the
tuple was handed straight to the converter, which calls `.exists()` on it.

These tests pin down the observable effects of a page conversion so the two
entry points can be unified without changing behaviour. They are also the
regression net for the tuple bug.

No live services: Redis is fakeredis, the database is in-memory SQLite with the
real models, and the converter / Elasticsearch / MinIO clients are mocks.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.database import Base
from shared.models import Job, JobStatus, Page

import workers.tasks as tasks


PARENT = "job-parent"


# ============================================
# Infrastructure
# ============================================

class RetryCalled(Exception):
    """Raised in place of celery's real retry so tests stay synchronous."""

    def __init__(self, exc=None):
        super().__init__(str(exc))
        self.exc = exc


@pytest.fixture
def session_local():
    """A sessionmaker over a single shared in-memory SQLite connection.

    StaticPool is required: the tasks open and close a session per step, and a
    plain in-memory SQLite gives every new connection its own empty database.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def converter():
    """A stand-in for DoclingConverter that keeps its input contract.

    The real `convert_to_markdown` does `if not file_path.exists()` first, so a
    mock that swallows any argument would hide the tuple bug entirely.
    """
    mock = MagicMock(name="converter")

    def convert_to_markdown(file_path, options=None):
        if not file_path.exists():  # AttributeError if handed a tuple
            raise FileNotFoundError(f"File not found: {file_path}")
        return {"markdown": "# Page content", "metadata": {"words": 2, "pages": 1}}

    mock.convert_to_markdown.side_effect = convert_to_markdown
    return mock


@pytest.fixture
def wired(monkeypatch, fake_redis, session_local, converter):
    """Patch every external dependency `workers.tasks` reaches for."""
    es = MagicMock(name="es_client")
    es.store_page_result.return_value = True
    es.store_job_result.return_value = True

    minio = MagicMock(name="minio_client")
    minio.bucket_results = "results"
    minio.bucket_pages = "pages"

    merge = MagicMock(name="merge_pages_task")

    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(tasks, "get_es_client", lambda: es)
    monkeypatch.setattr(tasks, "get_minio_client", lambda: minio)
    monkeypatch.setattr(tasks, "get_converter", lambda *a, **kw: converter)
    monkeypatch.setattr(tasks, "SessionLocal", session_local)
    monkeypatch.setattr(tasks, "merge_pages_task", merge)

    retries = []

    def fake_retry(exc=None, countdown=None, **kwargs):
        retries.append(SimpleNamespace(exc=exc, countdown=countdown))
        raise RetryCalled(exc)

    for task in (tasks.convert_page_task, tasks.process_page, tasks.split_pdf_task):
        monkeypatch.setattr(task, "retry", fake_retry)

    # get_converter is called with a preset once the tasks are unified; record
    # the call so the preset regression can be asserted.
    preset_calls = []
    monkeypatch.setattr(
        tasks,
        "get_converter",
        lambda *a, **kw: (preset_calls.append(kw.get("preset", a[0] if a else None)), converter)[1],
    )

    return SimpleNamespace(
        redis=fake_redis,
        es=es,
        minio=minio,
        merge=merge,
        converter=converter,
        retries=retries,
        preset_calls=preset_calls,
        session_local=session_local,
    )


def run_task(task, **kwargs):
    """Run a bind=True celery task body synchronously with a request context."""
    task.push_request(retries=0)
    try:
        return task.run(**kwargs)
    finally:
        task.pop_request()


def seed(session_local, redis, total_pages=1):
    """Create the parent job, its Page rows and the matching Redis state."""
    db = session_local()
    try:
        db.add(Job(id=PARENT, filename="doc.pdf", status=JobStatus.PROCESSING,
                   total_pages=total_pages, pages_completed=0, pages_failed=0))
        for n in range(1, total_pages + 1):
            db.add(Page(id=f"page-row-{n}", job_id=PARENT, page_number=n,
                        page_job_id=f"pagejob-{n}", status=JobStatus.PENDING))
        db.commit()
    finally:
        db.close()

    redis.set_job_status(job_id=PARENT, job_type="main", status="processing", progress=20)
    redis.set_job_pages(PARENT, total_pages)
    for n in range(1, total_pages + 1):
        redis.add_child_job(PARENT, "page", f"pagejob-{n}")


def get_page(session_local, page_number=1):
    db = session_local()
    try:
        return db.query(Page).filter(Page.job_id == PARENT,
                                     Page.page_number == page_number).first()
    finally:
        db.close()


def get_job(session_local):
    db = session_local()
    try:
        return db.query(Job).filter(Job.id == PARENT).first()
    finally:
        db.close()


# ============================================
# The critical constraint: task names are pinned
# ============================================

def test_task_names_are_pinned_to_the_historic_derived_names():
    """Renaming a task strands in-flight messages: `task_acks_late` plus
    `task_reject_on_worker_lost` makes them requeue and loop on NotRegistered.
    These strings must never change."""
    assert tasks.process_conversion.name == "workers.tasks.process_conversion"
    assert tasks.split_pdf_task.name == "workers.tasks.split_pdf_task"
    assert tasks.convert_page_task.name == "workers.tasks.convert_page_task"
    assert tasks.process_page.name == "workers.tasks.process_page"
    assert tasks.merge_pages_task.name == "workers.tasks.merge_pages_task"


# ============================================
# Both entry points produce the same effects
# ============================================

def _run_via_split_path(tmp_path, **_):
    page_file = tmp_path / "page_0001.pdf"
    page_file.write_bytes(b"%PDF-1.4 page one")
    run_task(
        tasks.convert_page_task,
        page_job_id="pagejob-1",
        parent_job_id=PARENT,
        page_number=1,
        page_file_path=str(page_file),
        options={},
    )
    return page_file


def _run_via_retry_path(tmp_path, monkeypatch, **_):
    source_pdf = tmp_path / "original.pdf"
    source_pdf.write_bytes(b"%PDF-1.4 whole document")
    extracted = tmp_path / "extracted_0001.pdf"
    extracted.write_bytes(b"%PDF-1.4 page one")

    splitter = MagicMock(name="PDFSplitter")
    # The real signature: Tuple[local_page_path, minio_path]
    splitter.return_value.extract_single_page.return_value = (extracted, "pages/x/page_0001.pdf")
    monkeypatch.setattr(tasks, "PDFSplitter", splitter)

    run_task(
        tasks.process_page,
        job_id="pagejob-1",
        parent_job_id=PARENT,
        pdf_path=str(source_pdf),
        page_number=1,
        options={},
    )
    return extracted


@pytest.mark.parametrize("run_entry_point", [_run_via_split_path, _run_via_retry_path],
                         ids=["split_path", "retry_path"])
def test_both_entry_points_produce_the_same_effects(wired, monkeypatch, tmp_path,
                                                    run_entry_point):
    seed(wired.session_local, wired.redis, total_pages=1)

    run_entry_point(tmp_path, monkeypatch=monkeypatch)

    page = get_page(wired.session_local)
    assert page.status == JobStatus.COMPLETED
    assert page.markdown_content == "# Page content"
    assert page.char_count == len("# Page content")
    assert page.completed_at is not None

    job = get_job(wired.session_local)
    assert job.pages_completed == 1

    status = wired.redis.get_job_status("pagejob-1")
    assert status["status"] == "completed"
    assert status["parent_job_id"] == PARENT
    assert status["page_number"] == 1

    kwargs = wired.es.store_page_result.call_args.kwargs
    assert kwargs["job_id"] == PARENT
    assert kwargs["page_number"] == 1
    assert kwargs["markdown_content"] == "# Page content"

    # last (only) page finished -> exactly one merge
    assert wired.merge.delay.call_count == 1
    assert wired.merge.delay.call_args.kwargs["parent_job_id"] == PARENT


# ============================================
# The tuple bug
# ============================================

def test_extracted_page_tuple_is_unpacked_before_conversion(wired, monkeypatch, tmp_path):
    """Regression: `extract_single_page` returns `(Path, Optional[str])`.

    Passing that tuple to the converter blows up with AttributeError on
    `file_path.exists()`. The converter must receive the Path.
    """
    seed(wired.session_local, wired.redis, total_pages=1)

    source_pdf = tmp_path / "original.pdf"
    source_pdf.write_bytes(b"%PDF-1.4 whole document")
    extracted = tmp_path / "extracted_0001.pdf"
    extracted.write_bytes(b"%PDF-1.4 page one")

    splitter = MagicMock(name="PDFSplitter")
    splitter.return_value.extract_single_page.return_value = (extracted, "pages/x/page_0001.pdf")
    monkeypatch.setattr(tasks, "PDFSplitter", splitter)

    try:
        run_task(
            tasks.process_page,
            job_id="pagejob-1",
            parent_job_id=PARENT,
            pdf_path=str(source_pdf),
            page_number=1,
            options={},
        )
        failure = None
    except RetryCalled as exc:
        failure = exc

    converted_path = wired.converter.convert_to_markdown.call_args.args[0]
    assert isinstance(converted_path, Path), (
        f"converter received {converted_path!r} - the (path, minio_path) tuple "
        "was not unpacked"
    )
    assert converted_path == extracted
    assert failure is None
    assert get_page(wired.session_local).status == JobStatus.COMPLETED


# ============================================
# Merge fan-in
# ============================================

def test_merge_is_enqueued_once_by_the_last_page(wired, tmp_path):
    seed(wired.session_local, wired.redis, total_pages=3)

    for n in (1, 2, 3):
        page_file = tmp_path / f"page_{n:04d}.pdf"
        page_file.write_bytes(b"%PDF-1.4")
        run_task(
            tasks.convert_page_task,
            page_job_id=f"pagejob-{n}",
            parent_job_id=PARENT,
            page_number=n,
            page_file_path=str(page_file),
            options={},
        )
        # merge only after the final page
        assert wired.merge.delay.call_count == (1 if n == 3 else 0)

    assert get_job(wired.session_local).pages_completed == 3


# ============================================
# Failure path
# ============================================

@pytest.mark.parametrize("run_entry_point", [_run_via_split_path, _run_via_retry_path],
                         ids=["split_path", "retry_path"])
def test_conversion_failure_marks_page_failed_and_retries(wired, monkeypatch, tmp_path,
                                                          run_entry_point):
    seed(wired.session_local, wired.redis, total_pages=1)
    wired.converter.convert_to_markdown.side_effect = RuntimeError("docling exploded")

    with pytest.raises(RetryCalled):
        run_entry_point(tmp_path, monkeypatch=monkeypatch)

    page = get_page(wired.session_local)
    assert page.status == JobStatus.FAILED
    assert "docling exploded" in page.error_message

    assert get_job(wired.session_local).pages_failed == 1
    assert wired.redis.get_job_status("pagejob-1")["status"] == "failed"
    assert len(wired.retries) == 1
    assert isinstance(wired.retries[0].exc, RuntimeError)
    assert wired.merge.delay.call_count == 0


# ============================================
# split_pdf_task fan-out
# ============================================

def test_split_pdf_task_creates_one_page_row_and_one_task_per_page(wired, monkeypatch,
                                                                   tmp_path):
    db = wired.session_local()
    try:
        db.add(Job(id=PARENT, filename="doc.pdf", status=JobStatus.PROCESSING))
        db.commit()
    finally:
        db.close()
    wired.redis.set_job_status(job_id=PARENT, job_type="main", status="processing", progress=20)

    source_pdf = tmp_path / "three_pages.pdf"
    source_pdf.write_bytes(b"%PDF-1.4")
    page_files = [
        (n, tmp_path / f"page_{n:04d}.pdf", f"pages/{PARENT}/page_{n:04d}.pdf")
        for n in (1, 2, 3)
    ]
    splitter = MagicMock(name="PDFSplitter")
    splitter.return_value.split_pdf.return_value = page_files
    monkeypatch.setattr(tasks, "PDFSplitter", splitter)

    convert = MagicMock(name="convert_page_task")
    monkeypatch.setattr(tasks, "convert_page_task", convert)

    run_task(
        tasks.split_pdf_task,
        split_job_id="split-1",
        parent_job_id=PARENT,
        file_path=str(source_pdf),
        options={},
    )

    db = wired.session_local()
    try:
        rows = db.query(Page).filter(Page.job_id == PARENT).order_by(Page.page_number).all()
        assert [r.page_number for r in rows] == [1, 2, 3]
        assert [r.minio_page_path for r in rows] == [p[2] for p in page_files]
        assert all(r.status == JobStatus.PENDING for r in rows)
    finally:
        db.close()

    assert convert.delay.call_count == 3
    assert [c.kwargs["page_number"] for c in convert.delay.call_args_list] == [1, 2, 3]
    assert [c.kwargs["parent_job_id"] for c in convert.delay.call_args_list] == [PARENT] * 3

    assert get_job(wired.session_local).total_pages == 3
    assert wired.redis.get_job_pages_total(PARENT) == 3
    assert len(wired.redis.get_page_jobs(PARENT)) == 3


# ============================================
# The preset regression
# ============================================

def test_docling_preset_from_options_reaches_the_converter(wired, tmp_path):
    """`convert_page_task` used to call `get_converter()` with no preset, so
    multi-page PDFs silently ignored `docling_preset`."""
    seed(wired.session_local, wired.redis, total_pages=1)
    page_file = tmp_path / "page_0001.pdf"
    page_file.write_bytes(b"%PDF-1.4")

    run_task(
        tasks.convert_page_task,
        page_job_id="pagejob-1",
        parent_job_id=PARENT,
        page_number=1,
        page_file_path=str(page_file),
        options={"docling_preset": "fast"},
    )

    assert "fast" in wired.preset_calls


# ============================================
# The unified entry point and its deprecated shim
# ============================================

def test_process_page_shim_maps_legacy_kwargs_onto_the_unified_task(monkeypatch):
    """The shim exists only to drain messages queued under the old task name.
    It must translate the old kwargs, not reimplement anything."""
    seen = {}

    def spy(task, **kwargs):
        seen.update(kwargs)
        seen["task"] = task
        return "forwarded"

    monkeypatch.setattr(tasks, "_run_page_conversion", spy)

    assert run_task(
        tasks.process_page,
        job_id="new-page-job",
        parent_job_id=PARENT,
        pdf_path="/tmp/original.pdf",
        page_number=7,
        options={"docling_preset": "fast"},
    ) == "forwarded"

    assert seen["page_job_id"] == "new-page-job"          # was job_id
    assert seen["source_pdf_path"] == "/tmp/original.pdf"  # was pdf_path
    assert seen["parent_job_id"] == PARENT
    assert seen["page_number"] == 7
    assert seen["options"] == {"docling_preset": "fast"}
    # retries stay on the shim's own task (identity check via name: the module
    # attribute is celery's lazy proxy, not the Task instance itself)
    assert seen["task"].name == "workers.tasks.process_page"


@pytest.mark.parametrize("kwargs", [
    {},
    {"page_file_path": "/tmp/p.pdf", "source_pdf_path": "/tmp/doc.pdf"},
], ids=["neither", "both"])
def test_exactly_one_page_source_is_required(wired, kwargs):
    with pytest.raises(ValueError, match="Exactly one of"):
        run_task(
            tasks.convert_page_task,
            page_job_id="pagejob-1",
            parent_job_id=PARENT,
            page_number=1,
            **kwargs,
        )


def test_extracted_page_is_cleaned_up_but_a_pre_split_page_is_not(wired, monkeypatch,
                                                                  tmp_path):
    """A page we extracted is our temp file; a page produced by split_pdf_task
    belongs to the job and is removed by merge_pages_task."""
    seed(wired.session_local, wired.redis, total_pages=1)
    extracted = _run_via_retry_path(tmp_path, monkeypatch=monkeypatch)
    assert not extracted.exists()

    wired.merge.reset_mock()
    seed_file = _run_via_split_path(tmp_path)
    assert seed_file.exists()


def test_extracted_page_is_cleaned_up_on_failure(wired, monkeypatch, tmp_path):
    seed(wired.session_local, wired.redis, total_pages=1)
    wired.converter.convert_to_markdown.side_effect = RuntimeError("docling exploded")

    with pytest.raises(RetryCalled):
        extracted = _run_via_retry_path(tmp_path, monkeypatch=monkeypatch)

    assert not (tmp_path / "extracted_0001.pdf").exists()
