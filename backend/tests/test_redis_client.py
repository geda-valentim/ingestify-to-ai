"""
Unit tests for shared.redis_client, backed by fakeredis.

Two areas matter most here:
  * verify_job_ownership() - it is the access-control primitive the API relies on.
  * calculate_job_progress() - the number every client polls.
"""

import pytest


class TestJobStatus:
    def test_roundtrip(self, fake_redis):
        fake_redis.set_job_status(job_id="j1", job_type="main", status="queued", progress=0)
        status = fake_redis.get_job_status("j1")
        assert status["status"] == "queued"
        assert status["type"] == "main"

    def test_missing_job_returns_none(self, fake_redis):
        assert fake_redis.get_job_status("does-not-exist") is None


class TestVerifyJobOwnership:
    """This is a security boundary. Every case that returns True is a case where
    one user is allowed to read another user's document."""

    def test_owner_is_authorized(self, fake_redis):
        fake_redis.set_job_owner("j1", "user-a")
        assert fake_redis.verify_job_ownership("j1", "user-a") is True

    def test_other_user_is_rejected(self, fake_redis):
        fake_redis.set_job_owner("j1", "user-a")
        assert fake_redis.verify_job_ownership("j1", "user-b") is False

    def test_unknown_job_is_rejected(self, fake_redis):
        assert fake_redis.verify_job_ownership("ghost", "user-a") is False

    def test_ownerless_job_is_rejected(self, fake_redis):
        """A job with no recorded owner must never authorize anyone.
        This is the shape of the DELETE /jobs/{id} IDOR: absent data must deny."""
        fake_redis.set_job_status(job_id="j1", job_type="main", status="completed", progress=100)
        assert fake_redis.verify_job_ownership("j1", "user-a") is False

    def test_child_job_inherits_parent_ownership(self, fake_redis):
        fake_redis.set_job_owner("parent", "user-a")
        fake_redis.set_job_status(
            job_id="page-1", job_type="page", status="completed",
            progress=100, parent_job_id="parent",
        )
        assert fake_redis.verify_job_ownership("page-1", "user-a") is True

    def test_child_job_of_another_user_is_rejected(self, fake_redis):
        fake_redis.set_job_owner("parent", "user-a")
        fake_redis.set_job_status(
            job_id="page-1", job_type="page", status="completed",
            progress=100, parent_job_id="parent",
        )
        assert fake_redis.verify_job_ownership("page-1", "user-b") is False

    def test_child_job_with_ownerless_parent_is_rejected(self, fake_redis):
        fake_redis.set_job_status(
            job_id="page-1", job_type="page", status="completed",
            progress=100, parent_job_id="parent",
        )
        assert fake_redis.verify_job_ownership("page-1", "user-a") is False


class TestCalculateJobProgress:
    """NOTE: CLAUDE.md documents a 10%/80%/10% split/pages/merge weighting.
    The implementation does no such thing - it is a flat completed/total ratio.
    These tests pin the ACTUAL behaviour; see docs/CODE_REVIEW.md."""

    def test_no_pages_registered_is_zero(self, fake_redis):
        assert fake_redis.calculate_job_progress("j1") == 0

    def test_no_pages_completed_is_zero(self, fake_redis):
        fake_redis.set_job_pages("j1", 4)
        for n in range(1, 5):
            fake_redis.set_page_status("j1", n, "queued")
        assert fake_redis.calculate_job_progress("j1") == 0

    def test_partial_completion(self, fake_redis):
        fake_redis.set_job_pages("j1", 4)
        fake_redis.set_page_status("j1", 1, "completed")
        fake_redis.set_page_status("j1", 2, "completed")
        fake_redis.set_page_status("j1", 3, "processing")
        fake_redis.set_page_status("j1", 4, "queued")
        assert fake_redis.calculate_job_progress("j1") == 50

    def test_all_pages_completed_is_100(self, fake_redis):
        fake_redis.set_job_pages("j1", 3)
        for n in range(1, 4):
            fake_redis.set_page_status("j1", n, "completed")
        assert fake_redis.calculate_job_progress("j1") == 100

    def test_failed_pages_do_not_count_as_progress(self, fake_redis):
        fake_redis.set_job_pages("j1", 2)
        fake_redis.set_page_status("j1", 1, "completed")
        fake_redis.set_page_status("j1", 2, "failed")
        assert fake_redis.calculate_job_progress("j1") == 50

    def test_progress_never_exceeds_100(self, fake_redis):
        fake_redis.set_job_pages("j1", 3)
        for n in range(1, 4):
            fake_redis.set_page_status("j1", n, "completed")
        assert 0 <= fake_redis.calculate_job_progress("j1") <= 100

    def test_result_is_an_int(self, fake_redis):
        """Clients render this directly; a float would leak into the UI."""
        fake_redis.set_job_pages("j1", 3)
        fake_redis.set_page_status("j1", 1, "completed")
        assert isinstance(fake_redis.calculate_job_progress("j1"), int)


class TestUserJobIndex:
    def test_add_and_list(self, fake_redis):
        fake_redis.add_job_to_user("user-a", "j1")
        fake_redis.add_job_to_user("user-a", "j2")
        assert set(fake_redis.get_user_jobs("user-a")) == {"j1", "j2"}

    def test_add_is_idempotent(self, fake_redis):
        fake_redis.add_job_to_user("user-a", "j1")
        fake_redis.add_job_to_user("user-a", "j1")
        assert fake_redis.get_user_jobs("user-a") == ["j1"]

    def test_remove(self, fake_redis):
        fake_redis.add_job_to_user("user-a", "j1")
        fake_redis.remove_job_from_user("user-a", "j1")
        assert fake_redis.get_user_jobs("user-a") == []

    def test_users_are_isolated(self, fake_redis):
        fake_redis.add_job_to_user("user-a", "j1")
        assert fake_redis.get_user_jobs("user-b") == []
