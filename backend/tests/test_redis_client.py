"""
Unit tests for shared.redis_client, backed by fakeredis.

Scope note: this module is a TTL cache and nothing else. Authorization is not
tested here because it is not implemented here - see tests/test_deps_authorization.py
for the coverage of api/deps.py, which owns ownership enforcement.

Progress weighting is likewise not tested here: the live formula is inline in
workers/tasks.py, not in this client.
"""


class TestJobStatus:
    def test_roundtrip(self, fake_redis):
        fake_redis.set_job_status(job_id="j1", job_type="main", status="queued", progress=0)
        status = fake_redis.get_job_status("j1")
        assert status["status"] == "queued"
        assert status["type"] == "main"

    def test_missing_job_returns_none(self, fake_redis):
        assert fake_redis.get_job_status("does-not-exist") is None


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
