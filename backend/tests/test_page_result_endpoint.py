"""Durable per-page Markdown survives cache expiry and unavailable search."""
from unittest.mock import MagicMock

import pytest

from api import routes
from shared.models import Job, JobStatus, Page
from tests.test_page_pdf_endpoint import app, db, users, no_redis, _get  # noqa: F401


def seed_page(db, owner, status=JobStatus.COMPLETED, markdown="# Saved page"):
    db.add(Job(id="main", user_id=owner.id, job_type="MAIN"))
    db.add(Page(job_id="main", page_number=1, page_job_id="page-job",
                status=status, markdown_content=markdown))
    db.commit()


@pytest.mark.parametrize("index_unavailable", [False, True])
@pytest.mark.parametrize("markdown", ["# Saved page", ""])
def test_persisted_page_survives_expired_cache(app, db, users, monkeypatch, index_unavailable, markdown):
    alice, _ = users
    seed_page(db, alice, markdown=markdown)
    es = MagicMock()
    es.get_page_result.return_value = None
    getter = MagicMock(return_value=es, side_effect=ConnectionError("index unavailable") if index_unavailable else None)
    monkeypatch.setattr(routes, "get_es_client", getter)
    redis = MagicMock(side_effect=AssertionError("persisted text does not need Redis"))
    monkeypatch.setattr(routes, "get_redis_client", redis)
    response = _get(app, "/jobs/main/pages/1/result", alice)
    assert response.status_code == 200
    assert response.json()["result"]["markdown"] == markdown
    assert response.json()["page_number"] == 1
    redis.assert_not_called()


def test_search_metadata_is_preserved_when_available(app, db, users, monkeypatch):
    alice, _ = users
    seed_page(db, alice)
    es = MagicMock()
    es.get_page_result.return_value = {"markdown_content": "# Saved page", "metadata": {"words": 3, "title": "Title"}}
    monkeypatch.setattr(routes, "get_es_client", lambda: es)
    response = _get(app, "/jobs/main/pages/1/result", alice)
    assert response.status_code == 200
    assert response.json()["result"]["metadata"] == {"words": 3, "title": "Title"}


@pytest.mark.parametrize("status,code", [(JobStatus.PENDING, 400), (JobStatus.PROCESSING, 400),
                                       (JobStatus.FAILED, 500), (JobStatus.CANCELLED, 400)])
def test_open_or_failed_page_does_not_publish_stale_text(app, db, users, monkeypatch, status, code):
    alice, _ = users
    seed_page(db, alice, status=status)
    getter = MagicMock()
    monkeypatch.setattr(routes, "get_es_client", getter)
    assert _get(app, "/jobs/main/pages/1/result", alice).status_code == code
    getter.assert_not_called()


@pytest.mark.parametrize("anonymous", [False, True])
def test_durable_page_still_requires_owner(app, db, users, monkeypatch, anonymous):
    alice, mallory = users
    seed_page(db, alice)
    getter = MagicMock()
    monkeypatch.setattr(routes, "get_es_client", getter)
    assert _get(app, "/jobs/main/pages/1/result", None if anonymous else mallory).status_code == (401 if anonymous else 404)
    getter.assert_not_called()


def test_legacy_page_uses_its_saved_job_id_when_parent_cache_is_gone(app, db, users, monkeypatch):
    alice, _ = users
    seed_page(db, alice, markdown=None)
    es = MagicMock()
    es.get_page_result.return_value = None
    redis = MagicMock()
    redis.get_job_status.return_value = {"status": "completed"}
    redis.get_job_result.return_value = {"markdown": "# Cached page", "metadata": {}}
    monkeypatch.setattr(routes, "get_es_client", lambda: es)
    monkeypatch.setattr(routes, "get_redis_client", lambda: redis)
    response = _get(app, "/jobs/main/pages/1/result", alice)
    assert response.status_code == 200
    assert response.json()["result"]["markdown"] == "# Cached page"
    redis.get_job_result.assert_called_once_with("page-job")
    redis.get_page_job_id_by_number.assert_not_called()
