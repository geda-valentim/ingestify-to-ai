"""Spec 0019: the first registered account of an installation becomes its single root user."""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api import auth_routes
from shared import admin, rate_limit, root
from shared.database import Base, _add_missing_columns
from shared.models import ROOT_SLOT, AdminAudit, User
from shared.schemas import UserCreate


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "hit", lambda *a, **k: None)


def configure(monkeypatch, *, environment="development", token=""):
    settings = SimpleNamespace(environment=environment, root_setup_token=token, admin_user_ids="")
    monkeypatch.setattr(root, "get_settings", lambda: settings)
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    return settings


def request():
    return SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.9"))


def register(db, name, setup_token=None):
    body = UserCreate(email=f"{name}@example.com", username=name, password="Secret123", setup_token=setup_token)
    return asyncio.run(auth_routes.register(body, request(), db))


def error_code(exc_info):
    return exc_info.value.detail["code"]


# --- CA1, CA7, CA8 ------------------------------------------------------------------------------


def test_first_account_is_root_and_the_next_ones_are_not(db, monkeypatch):
    configure(monkeypatch)
    first = register(db, "alice")
    second = register(db, "bruno")

    assert (first.is_root, first.is_admin) == (True, True)
    assert (second.is_root, second.is_admin) == (False, False)
    assert db.query(User).filter(User.root_slot == ROOT_SLOT).count() == 1


def test_root_creation_is_audited_without_secrets(db, monkeypatch):
    configure(monkeypatch, token="t0k3n")
    created = register(db, "alice", setup_token="t0k3n")

    rows = db.query(AdminAudit).filter_by(action="platform.root.created").all()
    assert [(r.actor_user_id, r.target_id, r.target_type) for r in rows] == [(str(created.id),) * 2 + ("user",)]
    assert "t0k3n" not in str(rows[0].after) and "Secret123" not in str(rows[0].after)


def test_a_plain_registration_writes_no_root_audit(db, monkeypatch):
    configure(monkeypatch)
    register(db, "alice")
    register(db, "bruno")
    assert db.query(AdminAudit).filter_by(action="platform.root.created").count() == 1


# --- CA2 -------------------------------------------------------------------------------------------


def test_the_database_refuses_a_second_root(db):
    db.add(User(email="a@x.io", username="aaa", hashed_password="h", root_slot=ROOT_SLOT))
    db.commit()
    db.add(User(email="b@x.io", username="bbb", hashed_password="h", root_slot=ROOT_SLOT))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add_all([User(email=f"{n}@x.io", username=n * 3, hashed_password="h") for n in "cd"])
    db.commit()  # many NULLs are fine


def test_losing_the_root_race_yields_a_plain_user(db, monkeypatch):
    """Another registration claims root between our check and our insert."""
    configure(monkeypatch)
    calls = {"n": 0}
    real = root.root_exists

    def racing_root_exists(session):
        calls["n"] += 1
        if calls["n"] == 1:
            # The rival commits its root right after our check
            other = sessionmaker(bind=session.get_bind())()
            other.add(User(email="rival@x.io", username="rival", hashed_password="h",
                           is_admin=True, root_slot=ROOT_SLOT))
            other.commit()
            other.close()
            return False
        return real(session)

    monkeypatch.setattr(root, "root_exists", racing_root_exists)
    loser = register(db, "alice")

    assert (loser.is_root, loser.is_admin) == (False, False)
    assert db.query(User).filter(User.root_slot == ROOT_SLOT).count() == 1
    assert db.query(AdminAudit).filter_by(action="platform.root.created").count() == 0


def test_a_duplicate_email_race_is_not_mistaken_for_the_root_race(db, monkeypatch):
    configure(monkeypatch)
    real_check = root.check_setup_token

    def check_then_a_rival_commits(*args, **kwargs):
        # After the duplicate pre-checks and the root check, a rival commits the same
        # email (but no root) right before our insert
        real_check(*args, **kwargs)
        other = sessionmaker(bind=db.get_bind())()
        other.add(User(email="alice@example.com", username="rival", hashed_password="h"))
        other.commit()
        other.close()

    monkeypatch.setattr(root, "check_setup_token", check_then_a_rival_commits)
    with pytest.raises(IntegrityError):
        register(db, "alice")
    assert db.query(User).filter(User.root_slot == ROOT_SLOT).count() == 0


# --- CA3 -------------------------------------------------------------------------------------------


def test_production_without_token_closes_registration_until_root_exists(db, monkeypatch):
    configure(monkeypatch, environment="production")
    with pytest.raises(HTTPException) as exc:
        register(db, "alice")
    assert exc.value.status_code == 403 and error_code(exc) == "ROOT_SETUP_TOKEN_REQUIRED"
    assert db.query(User).count() == 0


@pytest.mark.parametrize("environment", ["production", "development"])
@pytest.mark.parametrize("given", [None, "", "wrong", "s3cret-but-longer"])
def test_a_configured_token_must_match(db, monkeypatch, environment, given):
    configure(monkeypatch, environment=environment, token="s3cret")
    with pytest.raises(HTTPException) as exc:
        register(db, "alice", setup_token=given)
    assert exc.value.status_code == 403 and error_code(exc) == "ROOT_SETUP_TOKEN_INVALID"
    assert db.query(User).count() == 0


@pytest.mark.parametrize("environment", ["production", " Production ", "development"])
def test_the_right_token_creates_root(db, monkeypatch, environment):
    configure(monkeypatch, environment=environment, token="s3cret")
    assert register(db, "alice", setup_token="s3cret").is_root


def test_development_without_token_needs_none(db, monkeypatch):
    configure(monkeypatch)
    assert register(db, "alice").is_root


def test_the_token_is_ignored_once_root_exists(db, monkeypatch):
    configure(monkeypatch, environment="production", token="s3cret")
    register(db, "alice", setup_token="s3cret")
    later = register(db, "bruno", setup_token="anything")
    assert later.is_root is False


def test_the_token_is_compared_in_constant_time(monkeypatch):
    seen = []
    monkeypatch.setattr(root.hmac, "compare_digest", lambda a, b: seen.append((a, b)) or a == b)
    root.check_setup_token("abc", SimpleNamespace(environment="development", root_setup_token="abc"))
    assert seen == [(b"abc", b"abc")]


# --- CA4 -------------------------------------------------------------------------------------------


def test_root_stays_an_admin_even_with_is_admin_cleared(db, monkeypatch):
    configure(monkeypatch)
    user = User(email="r@x.io", username="root", hashed_password="h", is_admin=False, root_slot=ROOT_SLOT)
    assert admin.is_effective_admin(user)
    assert not admin.is_effective_admin(User(email="u@x.io", username="usr", hashed_password="h", is_admin=False))


# --- CA5 -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("is_active,is_admin", [(False, True), (True, False), (False, False)])
def test_root_cannot_be_deactivated_or_demoted(is_active, is_admin):
    target = User(id="r", root_slot=ROOT_SLOT, is_active=True, is_admin=True)
    with pytest.raises(root.RootError) as exc:
        root.refuse_root_change(target, SimpleNamespace(is_active=is_active, is_admin=is_admin))
    assert (exc.value.code, exc.value.status) == ("ROOT_IMMUTABLE", 409)


def test_other_users_can_still_be_changed():
    root.refuse_root_change(User(id="u", is_active=True, is_admin=True), SimpleNamespace(is_active=False, is_admin=False))
    root.refuse_root_change(User(id="r", root_slot=ROOT_SLOT), SimpleNamespace(is_active=True, is_admin=True))


def test_the_subject_state_route_refuses_to_touch_root(monkeypatch):
    """PUT /admin/access/subjects/{id}/state is the only app path that writes these flags."""
    from api import access_routes

    target = User(id="r", root_slot=ROOT_SLOT, is_active=True, is_admin=True)
    query = SimpleNamespace(filter_by=lambda **k: query, populate_existing=lambda: query,
                            with_for_update=lambda: query, first=lambda: target)
    fake_db = SimpleNamespace(query=lambda model: query, commit=lambda: pytest.fail("must not commit"))
    authority = SimpleNamespace(version=0)
    monkeypatch.setattr(access_routes, "ready", lambda: None)
    monkeypatch.setattr(access_routes, "invoke", lambda fn, *a, **k: authority)
    body = SimpleNamespace(expected_is_active=True, expected_is_admin=True, is_active=False, is_admin=True)

    with pytest.raises(HTTPException) as exc:
        access_routes.subject_state("r", body, user=SimpleNamespace(id="admin"), db=fake_db)
    assert exc.value.status_code == 409 and error_code(exc) == "ROOT_IMMUTABLE"
    assert (target.is_active, target.is_admin, authority.version) == (True, True, 0)


# --- CA6 -------------------------------------------------------------------------------------------


def test_setup_status_reports_only_root_and_token_need(db, monkeypatch):
    configure(monkeypatch, environment="production", token="s3cret")
    before = auth_routes.setup_status(db)
    assert before.model_dump() == {"root_exists": False, "setup_token_required": True}
    register(db, "alice", setup_token="s3cret")
    assert auth_routes.setup_status(db).model_dump() == {"root_exists": True, "setup_token_required": True}


@pytest.mark.parametrize("environment,token,required", [
    ("production", "", True), ("development", "", False), ("development", "x", True),
])
def test_setup_token_required_rule(environment, token, required):
    assert root.setup_token_required(SimpleNamespace(environment=environment, root_setup_token=token)) is required


# --- schema upgrade at boot ----------------------------------------------------------------------


def test_boot_upgrade_adds_root_slot_and_its_unique_index_to_an_old_users_table():
    from sqlalchemy import inspect, text

    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(255))"))
    _add_missing_columns(engine)
    _add_missing_columns(engine)  # idempotent

    inspector = inspect(engine)
    assert "root_slot" in {c["name"] for c in inspector.get_columns("users")}
    assert any(i["name"] == "uq_users_root_slot" and i["unique"] for i in inspector.get_indexes("users"))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, root_slot) VALUES ('a', 'a', 1)"))
        with pytest.raises(Exception):
            conn.execute(text("INSERT INTO users (id, email, root_slot) VALUES ('b', 'b', 1)"))
