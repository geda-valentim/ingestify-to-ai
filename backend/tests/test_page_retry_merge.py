"""
A page retry is a new attempt under a new page job id. The attempt's identity has
to move in MySQL (Page.page_job_id) and in the parent's cached child list
(job:{id}:status -> child_job_ids.page_job_ids) together, and the merge decision must
not depend on Redis:

- retry succeeds -> the MAIN job reaches the merge and COMPLETED;
- Redis expired meanwhile -> still merges (MySQL decides and holds the markdown);
- two retries in a row -> only the latest attempt is in the list;
- the superseded attempt finishing late is ignored (neither its result nor its failure).

SQLite with the real models, fakeredis through the real RedisClient.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shared import page_retry
from shared.models import Job, JobStatus, Page
import workers.tasks as tasks

from tests.test_tasks_page_conversion import (  # noqa: F401  (fixtures)
    PARENT, converter, get_job, get_page, run_task, seed, session_local, wired,
)

REAL_MERGE = tasks.merge_pages_task


@pytest.fixture
def world(wired, monkeypatch, tmp_path):
    """3 pages, the real merge wired behind merge_pages_task.delay, page retry plumbing"""
    seed(wired.session_local, wired.redis, total_pages=3)
    db = wired.session_local()
    job = db.query(Job).filter(Job.id == PARENT).first()
    job.minio_upload_path = f"uploads/{PARENT}/doc.pdf"
    db.commit()
    db.close()

    merges = []

    def merge_delay(**kw):
        merges.append(kw)
        REAL_MERGE.run(**kw)

    wired.merge.delay.side_effect = merge_delay
    monkeypatch.setattr(page_retry.engine_dispatch, "submit", lambda **kw: "queued")

    texts = {}

    def convert(file_path, options=None):
        return {"markdown": texts.get(Path(file_path).name, "# text"), "metadata": {"words": 2, "pages": 1}}

    wired.converter.convert_to_markdown.side_effect = convert

    class Minio:
        def download_file(self, bucket, key, file_path=None):
            Path(file_path).write_bytes(b"%PDF-1.4")
            return True

    monkeypatch.setattr(page_retry, "source_bucket", lambda minio, path: "uploads")

    splitter = MagicMock(name="PDFSplitter")

    def extract(source, number):
        out = tmp_path / f"extracted_{number}.pdf"
        out.write_bytes(b"%PDF-1.4")
        return out, None

    splitter.return_value.extract_single_page.side_effect = extract
    monkeypatch.setattr(tasks, "PDFSplitter", splitter)
    monkeypatch.setattr(tasks, "_remove_job_files", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "_purge_source_if_requested", lambda *a, **k: None)

    class World:
        pass

    w = World()
    w.wired, w.merges, w.texts, w.tmp_path, w.minio = wired, merges, texts, tmp_path, Minio()
    w.pdf = tmp_path

    def complete_page(n, page_job_id=None):
        f = tmp_path / f"page_{n:04d}.pdf"
        f.write_bytes(b"%PDF-1.4")
        return run_task(tasks.convert_page_task, page_job_id=page_job_id or f"pagejob-{n}", parent_job_id=PARENT,
                        page_number=n, page_file_path=str(f), options={})

    def fail_page(n, page_job_id=None):
        tasks._mark_page_failed("[t]", page_job_id or f"pagejob-{n}", PARENT, n, "boom")

    def retry(n):
        db = wired.session_local()
        try:
            job = db.query(Job).filter(Job.id == PARENT).first()
            pages = page_retry.locked_failed_pages(db, PARENT, [n])
            queued, failed = page_retry.requeue_pages(
                db, job, pages, user_id=None, remote_use=lambda: False, enqueue=lambda **kw: None, celery=None,
                minio_factory=lambda: w.minio, temp_root=str(tmp_path / "temp"), today_queue="q",
                redis_client=wired.redis, session_factory=wired.session_local)
        finally:
            db.close()
        assert not failed and len(queued) == 1
        return queued[0][1]

    def run_attempt(n, attempt_id):
        source = tmp_path / "original.pdf"
        source.write_bytes(b"%PDF-1.4")
        return run_task(tasks.process_page, job_id=attempt_id, parent_job_id=PARENT, pdf_path=str(source),
                        page_number=n, options={})

    w.complete_page, w.fail_page, w.retry, w.run_attempt = complete_page, fail_page, retry, run_attempt
    return w


def page_ids(redis):
    return redis.get_page_jobs(PARENT)


def settle_first_pass(w, failing=2):
    """Pages 1 and 3 complete, `failing` fails: the MAIN job is PARTIAL"""
    for n in (1, 2, 3):
        if n == failing:
            w.fail_page(n)
        else:
            w.complete_page(n)
    assert get_job(w.wired.session_local).status == JobStatus.PARTIAL
    assert w.merges == []


def test_retry_success_reaches_the_merge_and_completes_the_job(world):
    settle_first_pass(world)
    world.texts["extracted_2.pdf"] = "# retried page"

    new_id = world.retry(2)
    assert new_id != "pagejob-2"
    # SQL and the cached child list name the same, live attempt
    assert get_page(world.wired.session_local, 2).page_job_id == new_id
    assert page_ids(world.wired.redis) == ["pagejob-1", "pagejob-3", new_id] \
        or sorted(page_ids(world.wired.redis)) == sorted(["pagejob-1", "pagejob-3", new_id])
    assert "pagejob-2" not in page_ids(world.wired.redis)
    assert get_job(world.wired.session_local).status == JobStatus.PROCESSING

    out = world.run_attempt(2, new_id)

    assert out["status"] == "completed"
    assert len(world.merges) == 1
    job = get_job(world.wired.session_local)
    assert job.status == JobStatus.COMPLETED
    assert job.pages_completed == 3 and job.pages_failed == 0
    merged = world.wired.redis.get_job_result(PARENT)["markdown"]
    assert "# retried page" in merged


def test_retry_success_with_redis_expired_still_merges(world):
    settle_first_pass(world)
    new_id = world.retry(2)
    world.wired.redis.client.flushall()  # every cached key expired: child list, page statuses, results

    world.run_attempt(2, new_id)

    assert len(world.merges) == 1
    assert get_job(world.wired.session_local).status == JobStatus.COMPLETED
    # pages 1 and 3 had no result in Redis any more: their markdown came from MySQL
    assert world.wired.redis.get_job_result(PARENT)["metadata"]["pages"] == 3


def test_two_retries_in_a_row(world):
    settle_first_pass(world)
    first = world.retry(2)
    world.fail_page(2, first)  # the retry fails too
    assert get_job(world.wired.session_local).status == JobStatus.PARTIAL
    second = world.retry(2)

    assert len({"pagejob-2", first, second}) == 3
    ids = page_ids(world.wired.redis)
    assert second in ids and first not in ids and "pagejob-2" not in ids and len(ids) == 3
    assert get_page(world.wired.session_local, 2).retry_count == 2

    world.run_attempt(2, second)

    assert len(world.merges) == 1
    assert get_job(world.wired.session_local).status == JobStatus.COMPLETED


def test_late_result_of_the_superseded_attempt_is_ignored(world):
    settle_first_pass(world)
    new_id = world.retry(2)

    # the old attempt (a worker that outlived the failure mark) completes late
    late = world.run_attempt(2, "pagejob-2")
    assert late["status"] == "superseded"
    page = get_page(world.wired.session_local, 2)
    assert page.status == JobStatus.PENDING and page.page_job_id == new_id
    assert world.merges == []
    assert get_job(world.wired.session_local).status == JobStatus.PROCESSING

    # and fails late: the live attempt is not marked failed either
    world.fail_page(2, "pagejob-2")
    assert get_page(world.wired.session_local, 2).status == JobStatus.PENDING

    world.texts["extracted_2.pdf"] = "# live"
    world.run_attempt(2, new_id)
    assert len(world.merges) == 1

    # a superseded completion after the merge neither rewrites the page nor merges again
    world.texts["extracted_2.pdf"] = "# stale"
    assert world.run_attempt(2, "pagejob-2")["status"] == "superseded"
    assert len(world.merges) == 1
    assert get_page(world.wired.session_local, 2).markdown_content == "# live"
    assert get_job(world.wired.session_local).status == JobStatus.COMPLETED


def test_replace_page_job_is_a_noop_without_the_parent_in_redis(fake_redis):
    assert fake_redis.replace_page_job("missing", "a", "b") is False


def test_failed_enqueue_puts_the_cached_list_back(world, monkeypatch):
    settle_first_pass(world)

    def boom(**kw):
        raise RuntimeError("broker down")

    monkeypatch.setattr(page_retry.engine_dispatch, "submit", boom)
    db = world.wired.session_local()
    job = db.query(Job).filter(Job.id == PARENT).first()
    pages = page_retry.locked_failed_pages(db, PARENT, [2])
    queued, failed = page_retry.requeue_pages(
        db, job, pages, user_id=None, remote_use=lambda: False, enqueue=lambda **kw: None, celery=None,
        minio_factory=lambda: world.minio, temp_root=str(world.tmp_path / "temp"), today_queue="q",
        redis_client=world.wired.redis, session_factory=world.wired.session_local)
    db.close()

    assert failed and not queued
    assert get_page(world.wired.session_local, 2).page_job_id == "pagejob-2"
    ids = page_ids(world.wired.redis)
    assert "pagejob-2" in ids and len(ids) == 3
