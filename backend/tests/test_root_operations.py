"""Spec 0019 operations: `make_admin.py --root` (CA10) and the f1c90019d3e4 migration."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.database import Base
from shared.models import ROOT_SLOT, AdminAudit, User

ROOT = Path(__file__).resolve().parents[2]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def world(monkeypatch):
    engine = sa.create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    script = _load(ROOT / "scripts" / "make_admin.py", "make_admin_under_test")
    monkeypatch.setattr(script, "SessionLocal", Session)
    from shared.access import policy

    monkeypatch.setattr(policy, "enabled", lambda: False)
    return Session, script


def _add(Session, **fields):
    with Session() as db:
        db.add(User(hashed_password="h", **fields))
        db.commit()


def test_root_designates_an_existing_active_user_and_audits(world):
    Session, script = world
    _add(Session, id="u1", email="a@x.io", username="alice")
    assert script.make_admin(email="a@x.io", assume_yes=True, as_root=True) == 0
    with Session() as db:
        user = db.get(User, "u1")
        assert (user.root_slot, user.is_admin) == (ROOT_SLOT, True)
        assert db.query(AdminAudit).filter_by(action="platform.root.designated", target_id="u1").count() == 1


def test_root_designates_even_an_existing_admin(world):
    Session, script = world
    _add(Session, id="u1", email="a@x.io", username="alice", is_admin=True)
    assert script.make_admin(email="a@x.io", assume_yes=True, as_root=True) == 0
    with Session() as db:
        assert db.get(User, "u1").root_slot == ROOT_SLOT


def test_root_is_never_replaced(world):
    Session, script = world
    _add(Session, id="r", email="r@x.io", username="root", is_admin=True, root_slot=ROOT_SLOT)
    _add(Session, id="u1", email="a@x.io", username="alice")
    assert script.make_admin(email="a@x.io", assume_yes=True, as_root=True) == 1
    with Session() as db:
        assert db.get(User, "u1").root_slot is None and db.get(User, "r").root_slot == ROOT_SLOT


def test_root_must_be_active(world):
    Session, script = world
    _add(Session, id="u1", email="a@x.io", username="alice", is_active=False)
    assert script.make_admin(email="a@x.io", assume_yes=True, as_root=True) == 1
    with Session() as db:
        assert db.get(User, "u1").root_slot is None


def test_a_concurrent_root_claim_is_reported_not_raised(world, monkeypatch):
    Session, script = world
    _add(Session, id="u1", email="a@x.io", username="alice")
    import shared.root as root_module

    real = root_module.root_exists

    def rival_claims_after_the_check(db):
        answer = real(db)
        _add(Session, id="r", email="r@x.io", username="rival", is_admin=True, root_slot=ROOT_SLOT)
        return answer

    monkeypatch.setattr(root_module, "root_exists", rival_claims_after_the_check)
    assert script.make_admin(email="a@x.io", assume_yes=True, as_root=True) == 1
    with Session() as db:
        assert db.get(User, "u1").root_slot is None


# --- alembic f1c90019d3e4 ----------------------------------------------------------------------


def _run(engine, fn):
    revision = _load(ROOT / "alembic" / "versions" / "f1c90019d3e4_users_root_slot.py", "rev_0019")
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(revision, fn)()


def _shape(engine):
    inspector = sa.inspect(engine)
    names = {i["name"] for i in inspector.get_indexes("users")} | {
        u["name"] for u in inspector.get_unique_constraints("users")}
    return "root_slot" in {c["name"] for c in inspector.get_columns("users")}, "uq_users_root_slot" in names


def test_migration_round_trip_from_an_old_users_table():
    engine = sa.create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(255))"))
        conn.execute(sa.text("INSERT INTO users (id, email) VALUES ('a', 'a@x.io')"))
    _run(engine, "upgrade")
    _run(engine, "upgrade")  # idempotent
    assert _shape(engine) == (True, True)
    _run(engine, "downgrade")
    assert _shape(engine) == (False, False)
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT email FROM users")).scalar() == "a@x.io"
    _run(engine, "upgrade")
    assert _shape(engine) == (True, True)


def test_downgrade_of_a_table_built_by_create_all():
    engine = sa.create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    assert _shape(engine) == (True, True)
    _run(engine, "upgrade")  # nothing to do
    _run(engine, "downgrade")
    assert _shape(engine) == (False, False)
