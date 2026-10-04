"""
Who is an admin, and making the first one.

One rule decides it everywhere: the users.is_admin column OR the id in
ADMIN_USER_IDS. /auth/me now reports it, so the frontend can tell admins apart.

scripts/make_admin.py used to look a user up by username first, then email.
Usernames are free-form, so someone could register the username
"ops@corp.com" and be promoted when the operator meant the user with that email.
It now takes --email or --id and refuses when an email is also someone's username.
"""

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import auth_routes
from shared.admin import AdminPromotionError, admin_user_ids, find_user_to_promote, is_effective_admin
from shared.database import Base
from shared.models import User
from shared.schemas import UserResponse


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _user(db, username, email, is_admin=False):
    user = User(username=username, email=email, hashed_password="x", is_active=True, is_admin=is_admin)
    db.add(user)
    db.commit()
    return user


def _settings(ids=""):
    return SimpleNamespace(admin_user_ids=ids)


# --- the rule ------------------------------------------------------------------------


def test_admin_by_column_or_by_listed_id():
    column_admin = SimpleNamespace(id="a", is_admin=True)
    listed = SimpleNamespace(id="b", is_admin=False)
    regular = SimpleNamespace(id="c", is_admin=False)
    settings = _settings(" b , z ")

    assert admin_user_ids(settings) == {"b", "z"}
    assert is_effective_admin(column_admin, settings)
    assert is_effective_admin(listed, settings)
    assert not is_effective_admin(regular, settings)
    assert not is_effective_admin(None, settings)


def test_a_truthy_non_boolean_column_is_not_admin():
    # A mock or an unloaded attribute must never grant admin by accident
    assert not is_effective_admin(SimpleNamespace(id="a", is_admin="yes"), _settings())


# --- /auth/me and /register report it ---------------------------------------------------


def test_me_reports_an_admin_listed_in_admin_user_ids(db, monkeypatch):
    user = _user(db, "ops", "ops@example.com")
    monkeypatch.setattr("shared.admin.get_settings", lambda: _settings(user.id))

    me = asyncio.run(auth_routes.get_current_user_info(current_user=user))

    assert me.is_admin is True
    assert me.email == "ops@example.com"


def test_me_reports_a_regular_user_as_not_admin(db, monkeypatch):
    user = _user(db, "alice", "alice@example.com")
    monkeypatch.setattr("shared.admin.get_settings", lambda: _settings())

    assert asyncio.run(auth_routes.get_current_user_info(current_user=user)).is_admin is False


def test_user_response_never_takes_is_admin_from_the_column_alone(db, monkeypatch):
    user = _user(db, "root", "root@example.com", is_admin=True)
    monkeypatch.setattr("shared.admin.get_settings", lambda: _settings())

    assert UserResponse.for_user(user).is_admin is True


# --- finding the user to promote -----------------------------------------------------------


def test_promote_by_email(db):
    alice = _user(db, "alice", "alice@example.com")
    assert find_user_to_promote(db, email="alice@example.com").id == alice.id


def test_promote_by_id(db):
    alice = _user(db, "alice", "alice@example.com")
    assert find_user_to_promote(db, user_id=alice.id).id == alice.id


def test_a_username_impersonating_the_email_blocks_the_promotion(db):
    _user(db, "ops", "ops@corp.com")  # the real ops user
    _user(db, "ops@corp.com", "attacker@evil.example")  # registered a lookalike username

    with pytest.raises(AdminPromotionError, match="also the username of another account"):
        find_user_to_promote(db, email="ops@corp.com")


def test_an_email_that_only_exists_as_a_username_is_refused(db):
    _user(db, "ops@corp.com", "attacker@evil.example")

    with pytest.raises(AdminPromotionError, match="also the username"):
        find_user_to_promote(db, email="ops@corp.com")


def test_the_same_user_with_username_equal_to_email_is_fine(db):
    user = _user(db, "bob@example.com", "bob@example.com")
    assert find_user_to_promote(db, email="bob@example.com").id == user.id


@pytest.mark.parametrize("kwargs", [{}, {"email": "a@b.c", "user_id": "1"}])
def test_exactly_one_identifier_is_required(db, kwargs):
    with pytest.raises(AdminPromotionError, match="exactly one"):
        find_user_to_promote(db, **kwargs)


def test_unknown_users_are_reported(db):
    with pytest.raises(AdminPromotionError, match="No user has the email"):
        find_user_to_promote(db, email="nobody@example.com")
    with pytest.raises(AdminPromotionError, match="No user has id"):
        find_user_to_promote(db, user_id="missing")
