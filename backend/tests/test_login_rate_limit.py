"""Login and registration are rate limited (per IP) and accounts lock out after repeated failures."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import auth_routes
from shared import rate_limit


class FakeRedis:
    def __init__(self):
        self.values, self.ttls = {}, {}

    def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key, seconds):
        self.ttls[key] = seconds

    def ttl(self, key):
        return self.ttls.get(key, -1)

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)
        self.ttls.pop(key, None)


class BrokenRedis:
    def __getattr__(self, name):
        raise ConnectionError("redis down")


USER = SimpleNamespace(id="user-1", is_active=True)


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "_redis", lambda: fake)
    monkeypatch.setattr(auth_routes.settings, "rate_limit_per_minute", 100)
    monkeypatch.setattr(auth_routes.settings, "login_max_failed_attempts", 3)
    monkeypatch.setattr(auth_routes.settings, "login_lockout_seconds", 900)
    monkeypatch.setattr(auth_routes.settings, "jwt_secret_key", "k" * 64)
    return fake


@pytest.fixture
def credentials(monkeypatch):
    """Only 'alice' / 'right' is valid"""
    monkeypatch.setattr(
        auth_routes, "authenticate_user",
        lambda db, username, password: USER if (username.lower(), password) == ("alice", "right") else None,
    )


def request(ip="203.0.113.7"):
    return SimpleNamespace(client=SimpleNamespace(host=ip))


def login(username, password, ip="203.0.113.7"):
    return asyncio.run(auth_routes.login(request(ip), username=username, password=password, db=None))


def status_of(username, password, ip="203.0.113.7"):
    try:
        login(username, password, ip)
        return 200
    except HTTPException as e:
        return e.status_code


def test_account_locks_after_repeated_failures(redis, credentials):
    assert [status_of("alice", "wrong") for _ in range(3)] == [401, 401, 401]
    # Locked: even the right password is refused, case/whitespace variations included
    assert status_of("alice", "right") == 429
    assert status_of("  ALICE ", "right") == 429


def test_lockout_is_per_account(redis, credentials):
    for _ in range(3):
        status_of("mallory", "guess")
    assert status_of("alice", "right") == 200


def test_success_resets_failure_count(redis, credentials):
    assert status_of("alice", "wrong") == 401
    assert status_of("alice", "wrong") == 401
    assert status_of("alice", "right") == 200
    assert [status_of("alice", "wrong") for _ in range(2)] == [401, 401]
    assert status_of("alice", "right") == 200


def test_per_ip_limit(redis, credentials, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "rate_limit_per_minute", 5)
    statuses = [status_of(f"user{i}", "x") for i in range(6)]
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    assert status_of("alice", "right", ip="198.51.100.1") == 200  # other IPs unaffected


def test_429_has_retry_after(redis, credentials):
    for _ in range(3):
        status_of("alice", "wrong")
    with pytest.raises(HTTPException) as exc:
        login("alice", "right")
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0


def test_register_limited_per_ip(redis, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "register_limit_per_hour", 2)
    rate_limit.hit("register:ip", "203.0.113.7", 2, 3600)
    rate_limit.hit("register:ip", "203.0.113.7", 2, 3600)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_routes.register(SimpleNamespace(), request(), db=None))
    assert exc.value.status_code == 429


def test_fails_open_when_redis_is_down(monkeypatch, credentials):
    monkeypatch.setattr(rate_limit, "_redis", lambda: BrokenRedis())
    monkeypatch.setattr(auth_routes.settings, "jwt_secret_key", "k" * 64)
    assert status_of("alice", "right") == 200
    assert status_of("alice", "wrong") == 401
