"""
Spec 0018 slice 1: engines family in the catalog, the iam_bindings columns, and the
copy / reconciliation / validation of `access_role_grants` (CA1, CA18).
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from shared.access import policy, service
from shared.access.models import AuthorizationEpoch, RoleGrant
from shared.access.policy import PERMISSIONS as ENGINE_PERMISSIONS
from shared.config import get_settings
from shared.database import Base
from shared.iam import bindings, catalog, engine_bindings, migration
from shared.iam.decide import Decider, principal_for_user
from shared.iam.models import IamBinding
from shared.models import AdminAudit, AppMigration, User
from tests.test_execution_profiles import grant, world  # noqa: F401
from tests.test_iam_engine_equivalence import legacy_grant, legacy_state

CA1_FIELDS = (
    ("subject_id", "user_id"), ("role", "role"), ("permissions", "permissions"),
    ("condition_ref", "policy_revision_id"), ("delegation", "delegation"),
    ("parent_id", "parent_id"), ("granted_by", "granted_by"), ("expires_at", "expires_at"),
    ("revoked_at", "revoked_at"), ("version", "version"), ("created_at", "created_at"),
)


def _engine(factory):
    return factory.kw["bind"]


def _markers(factory):
    with factory() as db:
        return {m.name for m in db.query(AppMigration)}


def _epoch(factory):
    with factory() as db:
        return db.get(AuthorizationEpoch, 1).version


# -- catalog ------------------------------------------------------------------------


def test_the_six_0009_roles_are_the_engines_family_read_from_policy():
    assert set(catalog.ENGINE_ROLES) == set(policy.ROLES) == {
        "observer", "profile_editor", "runtime_configurator",
        "engine_operator", "access_admin", "connection_manager",
    }
    for key, role in catalog.ENGINE_ROLES.items():
        assert role.permissions == frozenset(policy.ROLES[key])
        assert role.family == "engines" and catalog.family(key) == "engines"
        assert key not in catalog.ROLES
    for key in catalog.ROLES:
        assert catalog.family(key) == "platform"
    assert catalog.family("nobody") is None
    # The 0014 assertions stand: platform roles hold platform permissions only.
    for role in catalog.ROLES.values():
        assert role.permissions <= catalog.PLATFORM_PERMISSIONS
        assert not role.permissions & ENGINE_PERMISSIONS
    with pytest.raises(KeyError):
        catalog.role("observer")
    described = {r["key"]: r for r in catalog.describe()["roles"]}
    assert {k for k, r in described.items() if r["family"] == "platform"} == set(catalog.ROLES)
    assert {k for k, r in described.items() if r["family"] == "engines"} == set(catalog.ENGINE_ROLES)
    assert described["observer"]["permissions"] == sorted(policy.ROLES["observer"])


# -- CA1: copy -----------------------------------------------------------------------


def test_every_grant_becomes_a_binding_with_the_same_id_and_fields(world):  # noqa: F811
    with world() as db:
        ids = legacy_state(db)
        epoch = db.get(AuthorizationEpoch, 1).version
    migration.upgrade_0018(_engine(world))
    assert {migration.MARKER_0018} <= _markers(world)
    assert _epoch(world) == epoch + 1
    with world() as db:
        grants = db.query(RoleGrant).all()
        assert len(grants) == len(ids)  # every fixture is one grant
        for g in grants:
            b = db.get(IamBinding, g.id)
            assert b is not None, g.id
            assert (b.subject_type, b.scope_type, b.scope_id) == ("user", "platform", None)
            for mine, theirs in CA1_FIELDS:
                assert getattr(b, mine) == getattr(g, theirs), (g.id, mine)
            assert b.permissions and set(b.permissions) <= catalog.ENGINE_ROLES[b.role].permissions
        # revoked_by comes from the 0009 audit row.
        assert db.get(IamBinding, ids["revoked"]).revoked_by == "bootstrap"
        assert db.get(IamBinding, ids["parent2"]).revoked_by == "bootstrap"
        assert db.get(IamBinding, ids["op_plan"]).revoked_by is None
        # Delegation and parent chain preserved.
        child = db.get(IamBinding, ids["child"])
        assert child.parent_id == ids["parent"]
        assert db.get(IamBinding, ids["parent"]).delegation["max_grant_seconds"] == 1800
        assert db.get(IamBinding, ids["cycle_a"]).parent_id == ids["cycle_b"]
        assert db.get(IamBinding, ids["cycle_b"]).parent_id == ids["cycle_a"]


def test_the_migration_is_idempotent_and_leaves_the_epoch_alone_when_nothing_changes(world):  # noqa: F811
    with world() as db:
        legacy_state(db)
    migration.upgrade_0018(_engine(world))
    epoch = _epoch(world)
    with _engine(world).connect() as conn:
        before = conn.execute(text("SELECT * FROM iam_bindings ORDER BY id")).all()
    migration.upgrade_0018(_engine(world))
    with _engine(world).begin() as conn:
        assert migration.reconcile_engine_grants(conn) == {"copied": 0, "restricted": 0}
    with _engine(world).connect() as conn:
        assert conn.execute(text("SELECT * FROM iam_bindings ORDER BY id")).all() == before
    assert _epoch(world) == epoch
    migration.validate_schema(_engine(world))


def test_platform_bindings_are_untouched_and_carry_no_engine_columns(world):  # noqa: F811
    with world() as db:
        legacy_state(db)
        db.add(IamBinding(id="platform-1", subject_type="user", subject_id="operator",
                          role="platform_operator", granted_by="bootstrap",
                          expires_at=datetime.utcnow() + timedelta(days=1)))
        db.commit()
    migration.upgrade_0018(_engine(world))
    with world() as db:
        b = db.get(IamBinding, "platform-1")
        assert (b.permissions, b.condition_ref, b.delegation, b.parent_id) == (None, None, None, None)


def test_reconciliation_only_restricts(world):  # noqa: F811
    with world() as db:
        ids = legacy_state(db)
    migration.upgrade_0018(_engine(world))
    with world() as db:
        # Old code during a rollback: shorter expiry and a revocation in the legacy
        # table; a widening attempt (later expiry, un-revoke) in the legacy table.
        soon = datetime.utcnow() + timedelta(minutes=1)
        db.get(RoleGrant, ids["op_plan"]).expires_at = soon
        db.get(RoleGrant, ids["op_b"]).revoked_at = datetime.utcnow()
        db.get(RoleGrant, ids["op_b"]).version = 7
        db.get(RoleGrant, ids["editor"]).expires_at = datetime.utcnow() + timedelta(days=300)
        db.get(RoleGrant, ids["revoked"]).revoked_at = None
        db.commit()
        editor_expiry = db.get(IamBinding, ids["editor"]).expires_at
    epoch = _epoch(world)
    with _engine(world).begin() as conn:
        assert migration.reconcile_engine_grants(conn) == {"copied": 0, "restricted": 2}
    assert _epoch(world) == epoch + 1
    with world() as db:
        assert db.get(IamBinding, ids["op_plan"]).expires_at == soon
        op_b = db.get(IamBinding, ids["op_b"])
        assert op_b.revoked_at is not None and op_b.version == 7
        assert db.get(IamBinding, ids["editor"]).expires_at == editor_expiry
        assert db.get(IamBinding, ids["revoked"]).revoked_at is not None
        assert [g.id for g in engine_bindings.grants(db, "operator")] == [ids["op_plan"]]


def test_grants_created_by_the_old_code_after_the_migration_are_copied(world):  # noqa: F811
    with world() as db:
        legacy_state(db)
    migration.upgrade_0018(_engine(world))
    with world() as db:
        late = legacy_grant(db, actor="observer", role="observer")["id"]
    with pytest.raises(RuntimeError, match="without an iam_binding"):
        migration.validate_schema(_engine(world))
    with _engine(world).begin() as conn:
        assert migration.reconcile_engine_grants(conn)["copied"] == 1
    migration.validate_schema(_engine(world))
    with world() as db:
        assert db.get(IamBinding, late).role == "observer"


def test_a_grant_with_a_missing_parent_or_condition_aborts_the_migration(world):  # noqa: F811
    with world() as db:
        g = legacy_grant(db, actor="observer", role="observer")["id"]
        db.execute(text("PRAGMA foreign_keys=OFF"))
        db.get(RoleGrant, g).parent_id = "vanished"
        db.commit()
    with pytest.raises(RuntimeError, match="missing parents"):
        migration.upgrade_0018(_engine(world))
    with world() as db:
        assert db.query(IamBinding).count() == 0
        assert migration.MARKER_0018 not in _markers(world)
        db.get(RoleGrant, g).parent_id = None
        db.get(RoleGrant, g).policy_revision_id = "vanished"
        db.commit()
    with pytest.raises(RuntimeError, match="condition_ref does not resolve"):
        migration.upgrade_0018(_engine(world))
    with world() as db:
        assert db.query(IamBinding).count() == 0


def test_a_tampered_binding_fails_validation(world):  # noqa: F811
    with world() as db:
        ids = legacy_state(db)
    migration.upgrade_0018(_engine(world))
    with world() as db:
        db.get(IamBinding, ids["editor"]).permissions = sorted(policy.ROLES["engine_operator"])
        db.commit()
    with _engine(world).begin() as conn:
        with pytest.raises(RuntimeError, match="permissions"):
            migration.reconcile_engine_grants(conn)


def test_a_grant_whose_role_left_the_engines_family_aborts_the_migration(world):  # noqa: F811
    with world() as db:
        g = legacy_grant(db, actor="observer", role="observer")["id"]
        db.get(RoleGrant, g).role = "legacy_role"
        db.commit()
    with pytest.raises(RuntimeError, match="outside the engines family"):
        migration.upgrade_0018(_engine(world))
    with world() as db:
        assert db.query(IamBinding).count() == 0
        assert migration.MARKER_0018 not in _markers(world)


# -- the platform family never sees an engines binding ---------------------------------


def test_the_decider_and_platform_listing_ignore_engines_bindings(world):  # noqa: F811
    with world() as db:
        ids = legacy_state(db)
    migration.upgrade_0018(_engine(world))
    with world() as db:
        # A corrupt platform binding carrying an engines column grants nothing.
        db.add(IamBinding(id="corrupt", subject_type="user", subject_id="operator",
                          role="platform_operator", granted_by="bootstrap",
                          permissions=["platform.stats.read"],
                          expires_at=datetime.utcnow() + timedelta(days=1)))
        db.add(IamBinding(id="auditor", subject_type="user", subject_id="observer",
                          role="platform_auditor", granted_by="bootstrap",
                          expires_at=datetime.utcnow() + timedelta(days=1)))
        # A copied grant whose role is in neither family is still an engines binding.
        db.add(IamBinding(id="orphan-role", subject_type="user", subject_id="operator",
                          role="legacy_role", permissions=["engines.read"],
                          condition_ref=db.get(IamBinding, ids["op_plan"]).condition_ref,
                          granted_by="bootstrap", expires_at=datetime.utcnow() + timedelta(days=1)))
        db.commit()
        decider = Decider(db)
        operator = principal_for_user(db.get(User, "operator"))
        assert decider.platform_roles(operator) == []
        assert decider.platform_permissions(operator) == frozenset()
        listed = bindings.list_bindings(db, db.get(User, "observer"), include_inactive=True,
                                        decider=Decider(db))
        assert {b["id"] for b in listed} == {"corrupt", "auditor"}
        with pytest.raises(bindings.IamError) as refused:
            bindings.revoke(db, db.get(User, "bootstrap"), ids["op_plan"], version=0,
                                    decider=Decider(db))
        assert refused.value.code == "BINDING_NOT_FOUND"
        with pytest.raises(bindings.IamError) as refused:
            bindings.revoke(db, db.get(User, "bootstrap"), "orphan-role", version=0,
                            decider=Decider(db))
        assert refused.value.code == "BINDING_NOT_FOUND"


# -- CA18: schema, downgrade, round trips ------------------------------------------


# iam_bindings as the 0014 revision created it, frozen: the "existing_0014" start
# state must not be produced by `_drop_columns_0018`, which is under test.
IAM_BINDINGS_0014 = (
    """CREATE TABLE iam_bindings (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        subject_type VARCHAR(32) NOT NULL,
        subject_id VARCHAR(80) NOT NULL,
        role VARCHAR(64) NOT NULL,
        scope_type VARCHAR(32) NOT NULL,
        scope_id VARCHAR(80),
        granted_by VARCHAR(36) NOT NULL REFERENCES users (id),
        expires_at DATETIME NOT NULL,
        revoked_at DATETIME,
        revoked_by VARCHAR(36) REFERENCES users (id),
        version INTEGER NOT NULL,
        created_at DATETIME NOT NULL
    )""",
    "CREATE INDEX ix_iam_bindings_subject ON iam_bindings (subject_type, subject_id, revoked_at)",
    "CREATE INDEX ix_iam_bindings_scope ON iam_bindings (scope_type, scope_id)",
)


def _strip_0018(engine):
    """Replace the fresh iam_bindings with the frozen 0014 one (no engines columns)."""
    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM iam_bindings")).scalar() == 0
        conn.execute(text("DROP TABLE iam_bindings"))
        for ddl in IAM_BINDINGS_0014:
            conn.execute(text(ddl))
    cols = {c["name"] for c in inspect(engine).get_columns("iam_bindings")}
    assert not cols & set(migration.COLUMNS_0018)


def _schema(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("iam_bindings")}
    fks = {fk["constrained_columns"][0]: fk["referred_table"]
           for fk in inspect(engine).get_foreign_keys("iam_bindings")}
    idx = {i["name"] for i in inspect(engine).get_indexes("iam_bindings")}
    return cols, fks, idx


def _drop_every_table(engine):
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in inspect(conn).get_table_names():
            conn.execute(text(f"DROP TABLE `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


@pytest.fixture(params=["sqlite", "mysql"])
def migration_world(request, world):  # noqa: F811
    """
    The CA18 round trip on SQLite and on InnoDB. MySQL is opt-in like the other
    InnoDB gates (ENGINE_CONTROL_TEST_DATABASE_URL naming a disposable
    engine_control_test_* database): there DDL commits implicitly and an index
    backing a foreign key cannot be dropped before the key.
    """
    if request.param == "sqlite":
        yield world
        return
    from tests.test_execution_profiles_migration import mysql_url

    sql = create_engine(mysql_url(), pool_pre_ping=True)
    _drop_every_table(sql)
    Base.metadata.create_all(sql)
    # The synthetic users, engines and epoch of the shared fixture.
    with world() as source, sql.begin() as target:
        for table in Base.metadata.sorted_tables:
            rows = source.execute(table.select()).mappings().all()
            if rows:
                target.execute(table.insert(), [dict(row) for row in rows])
    yield sessionmaker(bind=sql)
    _drop_every_table(sql)
    sql.dispose()


@pytest.mark.parametrize("start", ["new", "existing_0014"])
def test_upgrade_downgrade_upgrade_round_trip(migration_world, start, settings_off):
    world = migration_world
    engine = _engine(world)
    with world() as db:
        ids = legacy_state(db)
    if start == "existing_0014":
        _strip_0018(engine)
        with pytest.raises(RuntimeError, match="0018"):
            migration.validate_schema(engine)
    migration.upgrade_0018(engine)
    cols, fks, idx = _schema(engine)
    assert set(migration.COLUMNS_0018) <= cols
    assert fks["condition_ref"] == "access_policy_revisions" and fks["parent_id"] == "iam_bindings"
    assert migration.INDEX_0018 in idx
    migration.validate_schema(engine)
    with world() as db:
        snapshot = sorted((b.id, b.version, b.revoked_at) for b in db.query(IamBinding))

    # Changes through the new store, then downgrade: the mirror gets the most
    # restrictive state, and a binding it lacks.
    with world() as db:
        b = db.get(IamBinding, ids["op_plan"])
        b.revoked_at, b.version, b.revoked_by = datetime.utcnow(), b.version + 1, "bootstrap"
        # As the unified revoke route (CA12) audits it: the only trace of the
        # revoker once the downgrade drops the binding.
        db.add(AdminAudit(actor_user_id="bootstrap", auth_method="jwt", action="iam.binding.revoke",
                          target_type="iam_binding", target_id=ids["op_plan"]))
        parent = db.get(IamBinding, ids["parent"])
        db.add(IamBinding(id="new-child", subject_type="user", subject_id="child2",
                          role="observer", permissions=["engines.read"],
                          condition_ref=parent.condition_ref, parent_id=parent.id,
                          granted_by="delegate", expires_at=datetime.utcnow() + timedelta(minutes=5)))
        db.add(IamBinding(id="platform-1", subject_type="user", subject_id="operator",
                          role="platform_operator", granted_by="bootstrap",
                          expires_at=datetime.utcnow() + timedelta(days=1)))
        db.commit()
    with pytest.raises(RuntimeError, match="outside the platform family"):
        migration.downgrade(engine)
    epoch = _epoch(world)
    migration.downgrade_0018(engine)
    assert _epoch(world) == epoch + 1
    cols, fks, idx = _schema(engine)
    assert not cols & set(migration.COLUMNS_0018) and migration.INDEX_0018 not in idx
    assert migration.MARKER_0018 not in _markers(world)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id FROM iam_bindings")).scalars().all() == ["platform-1"]
    with world() as db:
        assert db.get(RoleGrant, ids["op_plan"]).revoked_at is not None
        assert db.get(RoleGrant, ids["op_plan"]).version == 1
        assert db.get(RoleGrant, "new-child").parent_id == ids["parent"]

    # Downgrading again is a no-op; upgrading again restores the same bindings.
    migration.downgrade_0018(engine)
    migration.upgrade_0018(engine)
    migration.upgrade_0018(engine)
    migration.validate_schema(engine)
    with world() as db:
        again = {b.id: b for b in db.query(IamBinding)}
        assert set(again) == {i for i, *_ in snapshot} | {"new-child", "platform-1"}
        assert again[ids["op_plan"]].revoked_at is not None
        assert again[ids["op_plan"]].revoked_by == "bootstrap"
        assert again["platform-1"].permissions is None


@pytest.fixture
def settings_off(monkeypatch):
    monkeypatch.setattr(get_settings(), "iam_mode", "off")


def test_the_0014_migration_still_creates_the_full_table_on_a_new_database():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
    migration.upgrade(engine)
    cols, fks, idx = _schema(engine)
    assert set(migration.COLUMNS_0018) <= cols and migration.INDEX_0018 in idx
    engine.dispose()


def test_upgrade_0018_requires_0014_and_0009():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
    with pytest.raises(RuntimeError, match="0014"):
        migration.upgrade_0018(engine)
    migration.upgrade(engine)
    with pytest.raises(RuntimeError, match="0009"):
        migration.upgrade_0018(engine)
    engine.dispose()


def test_alembic_has_a_single_head_after_the_0018_revision():
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    # Spec 0019 (users.root_slot) now follows 0018 as the single head.
    assert scripts.get_heads() == ["f1c90019d3e4"]
    assert scripts.get_revision("f1c90019d3e4").down_revision == "d4e80018a2b6"
    assert scripts.get_revision("d4e80018a2b6").down_revision == "03e70014b8c5"


def test_a_full_create_all_schema_validates():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(AuthorizationEpoch(id=1, version=0))
        db.commit()
    migration.validate_schema(engine)
    engine.dispose()
