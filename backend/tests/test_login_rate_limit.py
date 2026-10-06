"""Login and registration are rate limited (per IP) and accounts lock out after repeated failures."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import auth_routes
from shared import rate_limit


class FakePipeline:
    def __init__(self, redis):
        self.redis, self.ops = redis, []

    def set(self, *args, **kwargs):
        self.ops.append(("set", args, kwargs))

    def incr(self, *args):
        self.ops.append(("incr", args, {}))

    def execute(self):
        return [getattr(self.redis, name)(*args, **kwargs) for name, args, kwargs in self.ops]


class FakeRedis:
    def __init__(self):
        self.values, self.ttls = {}, {}

    def pipeline(self, transaction=True):
        assert transaction, "counter creation and expiry must be atomic"
        return FakePipeline(self)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return None
        self.values[key] = value
        if ex:
            self.ttls[key] = ex
        return True

    def incr(self, key):
        self.values[key] = int(self.values.get(key, 0)) + 1
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


ALIASES = {"alice": "user-1", "alice@example.com": "user-1"}


@pytest.fixture
def credentials(monkeypatch):
    """Only alice (username or email) / 'right' is valid"""
    monkeypatch.setattr(
        auth_routes, "authenticate_user",
        lambda db, username, password: USER if (username.strip().lower() in ALIASES and password == "right") else None,
    )
    # Resolve username/email to the account like the real lookup does
    monkeypatch.setattr(
        auth_routes, "_lockout_identity",
        lambda db, login: f"user:{ALIASES[login.strip().lower()]}" if login.strip().lower() in ALIASES
        else f"name:{login.strip().lower()}",
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


def test_username_and_email_share_the_lockout(redis, credentials):
    assert [status_of(login, "wrong") for login in ("alice", "alice@example.com", "ALICE")] == [401, 401, 401]
    assert status_of("alice@example.com", "right") == 429
    assert status_of("alice", "right") == 429


def test_counters_always_expire(redis, credentials):
    status_of("alice", "wrong")
    status_of("203.0.113.9-user", "x", ip="203.0.113.9")
    assert set(redis.values) == set(redis.ttls)  # every counter was created with a TTL


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


def test_fails_closed_when_redis_is_down(monkeypatch, credentials):
    monkeypatch.setattr(rate_limit, "_redis", lambda: BrokenRedis())
    monkeypatch.setattr(auth_routes.settings, "jwt_secret_key", "k" * 64)
    assert status_of("alice", "right") == 503
    assert status_of("alice", "wrong") == 503


def test_lockout_identity_resolves_username_and_email_to_the_user(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from shared.database import Base
    from shared.models import User

    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(User(id="u-42", email="Alice@Example.com", username="Alice", hashed_password="x"))
    db.commit()

    keys = {auth_routes._lockout_identity(db, login) for login in ("alice", " ALICE ", "alice@example.com")}
    assert keys == {"user:u-42"}
    assert auth_routes._lockout_identity(db, "nobody") == "name:nobody"


def test_account_reservation_bounds_inflight_attempts(redis, credentials, monkeypatch):
    """A distributed budget exists even before in-flight bcrypt checks finish."""
    for _ in range(3):
        rate_limit.hit("login:account", "user:user-1", 3, 900)
    assert status_of("alice", "wrong", ip="198.51.100.9") == 429
    assert redis.get(rate_limit._key("login:failed", "user:user-1")) is None


def test_failure_record_and_reset_do_not_fail_open(monkeypatch):
    monkeypatch.setattr(rate_limit, "_redis", lambda: BrokenRedis())
    for operation in (
        lambda: rate_limit.record_failure("login:failed", "user:1", 900),
        lambda: rate_limit.reset("login:failed", "user:1"),
        lambda: rate_limit.check_failures("login:failed", "user:1", 3),
    ):
        with pytest.raises(HTTPException) as exc:
            operation()
        assert exc.value.status_code == 503
        assert exc.value.headers["Retry-After"] == "30"


@pytest.mark.parametrize("address,expected", [
    ("2001:db8:0:0::1", "2001:db8::1"),
    ("::ffff:203.0.113.7", "203.0.113.7"),
])
def test_ip_normalization(address, expected):
    assert rate_limit.client_ip(request(address)) == expected


def test_missing_peer_does_not_create_unlimited_shared_identity():
    with pytest.raises(HTTPException) as exc:
        rate_limit.client_ip(SimpleNamespace(client=None))
    assert exc.value.status_code == 503


async def _http_login(peer, headers, middleware=True):
    import httpx
    from fastapi import FastAPI
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    from shared.database import get_db

    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/auth")
    app.dependency_overrides[get_db] = lambda: None
    # The trusted value models the fixed private IP of the ingress container.
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts=["172.30.0.5"]) if middleware else app
    transport = httpx.ASGITransport(app=wrapped, client=(peer, 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/auth/login", data={"username": "alice", "password": "wrong"}, headers=headers)


def test_asgi_untrusted_peer_cannot_spoof_forwarded_headers(redis, credentials, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "rate_limit_per_minute", 2)
    monkeypatch.setattr(auth_routes.settings, "login_max_failed_attempts", 100)
    statuses = [asyncio.run(_http_login("203.0.113.7", {
        "X-Forwarded-For": f"198.51.100.{i}",
        "CF-Connecting-IP": f"198.51.100.{i}",
        "X-Real-IP": f"198.51.100.{i}",
    })).status_code for i in range(1, 4)]
    assert statuses == [401, 401, 429]
    assert redis.get(rate_limit._key("login:ip", "203.0.113.7")) == 3


def test_asgi_trusted_ingress_keeps_distinct_client_budgets(redis, credentials, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "rate_limit_per_minute", 1)
    monkeypatch.setattr(auth_routes.settings, "login_max_failed_attempts", 100)
    assert asyncio.run(_http_login("172.30.0.5", {"X-Forwarded-For": "203.0.113.7"})).status_code == 401
    assert asyncio.run(_http_login("172.30.0.5", {"X-Forwarded-For": "203.0.113.8"})).status_code == 401
    assert asyncio.run(_http_login("172.30.0.5", {"X-Forwarded-For": "203.0.113.7"})).status_code == 429


def test_asgi_forwarded_chain_uses_nearest_untrusted_hop(redis, credentials, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "rate_limit_per_minute", 1)
    monkeypatch.setattr(auth_routes.settings, "login_max_failed_attempts", 100)
    # An arbitrary leftmost value cannot change the actual nearest client.
    assert asyncio.run(_http_login("172.30.0.5", {"X-Forwarded-For": "198.51.100.1, 203.0.113.7"})).status_code == 401
    assert asyncio.run(_http_login("172.30.0.5", {"X-Forwarded-For": "198.51.100.2, 203.0.113.7"})).status_code == 429


def test_asgi_redis_outage_returns_retryable_503(monkeypatch, credentials):
    monkeypatch.setattr(rate_limit, "_redis", lambda: BrokenRedis())
    response = asyncio.run(_http_login("203.0.113.7", {}))
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"



def test_success_cannot_issue_token_if_counter_reset_fails(redis, credentials, monkeypatch):
    def broken_delete(key):
        raise ConnectionError("redis down after bcrypt")
    monkeypatch.setattr(redis, "delete", broken_delete)
    issued = []
    monkeypatch.setattr(auth_routes, "create_access_token", lambda **kwargs: issued.append(kwargs))
    assert status_of("alice", "right") == 503
    assert issued == []


def test_lockout_identity_preserves_username_precedence_over_email(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from shared.database import Base
    from shared.models import User

    engine = create_engine(f"sqlite:///{tmp_path / 'aliases.db'}")
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as db:
        # Insert the email match first: the old unordered OR returned it.
        db.add(User(id="email-owner", email="alice@example.com", username="other", hashed_password="x"))
        db.add(User(id="name-owner", email="different@example.com", username="alice@example.com", hashed_password="x"))
        db.commit()
        assert auth_routes._lockout_identity(db, "alice@example.com") == "user:name-owner"
        assert auth_routes._lockout_identity(db, "different@example.com") == "user:name-owner"
