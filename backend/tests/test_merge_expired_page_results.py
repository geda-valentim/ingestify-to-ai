"""
merge_pages_task with page results that expired from the Redis cache.

Redis is a TTL cache only: the durable copy of a page is its MySQL row. A merge
must rebuild an expired page from it, and must never publish a partial document
as COMPLETED when a page is unrecoverable.
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.database import Base
from shared.models import Job, JobStatus, Page
from workers import tasks

JOB = "job-main"
FULL = "page 1\n\n---\n\npage 2\n\n---\n\npage 3"


@pytest.fixture
def env(monkeypatch, fake_redis):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    es = MagicMock()
    es.store_job_result.return_value = True
    monkeypatch.setattr(tasks, "SessionLocal", Session)
    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(tasks, "get_es_client", lambda: es)
    monkeypatch.setattr(tasks, "_remove_job_files", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "_purge_source_if_requested", lambda *a, **k: None)
    monkeypatch.setattr(tasks.conversion_assets, "durable_options", lambda *a, **k: {})
    monkeypatch.setattr(tasks.conversion_assets, "wants_assets", lambda *a, **k: False)
    from workers import figure_tasks
    monkeypatch.setattr(figure_tasks, "wanted", lambda *a, **k: False)
    return Session, fake_redis, es


def seed(env, pages=3, expire=(), durable=True, expire_status=()):
    Session, redis, _ = env
    with Session() as db:
        db.add(Job(id=JOB, user_id=None, filename="a.pdf", name="a.pdf", job_type="MAIN",
                   source_type="file", status=JobStatus.PROCESSING, total_pages=pages))
        for n in range(1, pages + 1):
            db.add(Page(job_id=JOB, page_number=n, page_job_id=f"p{n}", status=JobStatus.COMPLETED,
                        markdown_content=f"page {n}" if durable else None))
        db.commit()
    redis.set_job_status(job_id=JOB, job_type="main", status="processing")
    for n in range(1, pages + 1):
        redis.set_job_status(job_id=f"p{n}", job_type="page", status="completed",
                             parent_job_id=JOB, page_number=n)
        redis.set_job_result(f"p{n}", {"markdown": f"page {n}", "metadata": {"words": 2}})
        redis.add_child_job(JOB, "page", f"p{n}")
    for n in expire:
        redis.client.delete(f"job:p{n}:result")
    for n in expire_status:
        redis.client.delete(f"job:p{n}:status")


def merge():
    return tasks.merge_pages_task.run(merge_job_id="m1", parent_job_id=JOB)


def job_status(env):
    with env[0]() as db:
        return db.get(Job, JOB).status


def test_normal_path_unchanged(env):
    seed(env)
    assert merge()["pages_merged"] == 3
    assert env[2].store_job_result.call_args.kwargs["markdown_content"] == FULL
    assert job_status(env) == JobStatus.COMPLETED


def test_expired_result_rebuilt_from_page_row(env):
    seed(env, expire=(2,))
    merge()
    assert env[2].store_job_result.call_args.kwargs["markdown_content"] == FULL
    assert job_status(env) == JobStatus.COMPLETED


def test_expired_status_and_result_rebuilt(env):
    seed(env, expire=(2,), expire_status=(2,))
    merge()
    assert env[2].store_job_result.call_args.kwargs["markdown_content"] == FULL
    assert env[2].store_job_result.call_args.kwargs["total_pages"] == 3


def assert_partial_nothing_published(env, failed=(2,)):
    assert job_status(env) == JobStatus.PARTIAL
    env[2].store_job_result.assert_not_called()
    assert env[1].get_job_result(JOB) is None
    with env[0]() as db:
        for n in failed:
            page = db.query(Page).filter(Page.job_id == JOB, Page.page_number == n).one()
            assert page.status == JobStatus.FAILED
            assert "retry the page" in page.error_message
        assert db.get(Job, JOB).pages_failed == len(failed)


def test_unrecoverable_page_ends_partial_without_a_retry(env, monkeypatch):
    seed(env, expire=(2,), durable=False)
    retry = MagicMock()
    monkeypatch.setattr(tasks.merge_pages_task, "retry", retry)
    purged = MagicMock()
    monkeypatch.setattr(tasks, "_purge_source_if_requested", purged)

    out = merge()

    assert out["incomplete"] is True and out["pages_failed"] == [2]
    assert_partial_nothing_published(env)
    retry.assert_not_called()
    purged.assert_not_called()


def test_a_page_without_a_completed_row_is_missing_not_skipped(env):
    seed(env, expire=(2,))
    with env[0]() as db:
        page = db.query(Page).filter(Page.job_id == JOB, Page.page_number == 2).one()
        page.status = JobStatus.PROCESSING
        db.commit()
    merge()
    assert job_status(env) != JobStatus.COMPLETED
    env[2].store_job_result.assert_not_called()


def test_figure_job_cannot_rebuild_from_rows(env, monkeypatch):
    from workers import figure_tasks
    monkeypatch.setattr(figure_tasks, "wanted", lambda *a, **k: True)
    begin = MagicMock()
    monkeypatch.setattr(figure_tasks, "begin", begin)
    seed(env, expire=(2,))
    merge()
    begin.assert_not_called()
    assert_partial_nothing_published(env)


def test_asset_job_cannot_rebuild_from_rows(env, monkeypatch):
    monkeypatch.setattr(tasks.conversion_assets, "wants_assets", lambda *a, **k: True)
    combine = MagicMock()
    monkeypatch.setattr(tasks.conversion_assets, "combine_pages", combine)
    seed(env, expire=(2,))
    merge()
    combine.assert_not_called()
    assert_partial_nothing_published(env)


def test_blank_page_is_kept(env):
    seed(env, expire=(2,))
    with env[0]() as db:
        db.query(Page).filter(Page.job_id == JOB, Page.page_number == 2).one().markdown_content = ""
        db.commit()
    assert merge()["pages_merged"] == 3
    assert env[2].store_job_result.call_args.kwargs["markdown_content"] == "page 1\n\n---\n\n\n\n---\n\npage 3"
    assert job_status(env) == JobStatus.COMPLETED


def test_total_pages_unknown_falls_back_to_the_cache(env):
    seed(env)
    with env[0]() as db:
        db.get(Job, JOB).total_pages = None
        db.commit()
        assert tasks._all_pages_completed(db, JOB) is None
    assert env[1].all_page_jobs_completed(JOB) is True


def test_all_pages_completed_counts_distinct_page_numbers(env):
    seed(env, pages=2)
    with env[0]() as db:
        assert tasks._all_pages_completed(db, JOB) is True
        db.get(Job, JOB).total_pages = 3
        db.commit()
        assert tasks._all_pages_completed(db, JOB) is False  # 2 distinct page numbers of 3


def test_figure_stage_still_begins_when_all_cached(env, monkeypatch):
    from workers import figure_tasks
    monkeypatch.setattr(figure_tasks, "wanted", lambda *a, **k: True)
    begin = MagicMock()
    monkeypatch.setattr(figure_tasks, "begin", begin)
    seed(env)
    for n in (1, 2, 3):
        env[1].set_job_result(f"p{n}", {"markdown": f"page {n}", "_figures": [{"n": n}], "metadata": {}})
    assert merge()["describing_figures"] is True
    begin.assert_called_once()
