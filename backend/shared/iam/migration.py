"""
Explicit, additive IAM migrations.

0014 (spec 0014 §4.8): only `CREATE TABLE iam_bindings`, recorded as the marker
`0014_iam_bindings` in `app_migrations`. No pre-existing row is touched.
Reversible with `downgrade` (DROP TABLE) once `IAM_MODE=off` and no binding
outside the platform family is left.

0018 (spec 0018 §4.2): the engines family moves into `iam_bindings`.

- DDL (`COLUMNS_0018`): `permissions`, `condition_ref`, `delegation`, `parent_id`,
  each added only if absent (on a new database the 0014 revision's `create_all`
  already creates them), the two foreign keys `fk_iam_bindings_condition_ref` and
  `fk_iam_bindings_parent` only if absent, and `ix_iam_bindings_subject_role`.
- Data, in a transaction of its own after the DDL (MySQL commits DDL implicitly):
  `reconcile_engine_grants` copies every `access_role_grants` row into a binding
  with the **same id** (parents first), restricts bindings to the most restrictive
  of the two tables, validates, and bumps the 0009 epoch when anything changed.
  The marker `0018_engine_bindings` is written last.

Reconciliation runs on every upgrade regardless of the marker, and only ever
restricts: revocations made by the pre-0018 code during a rollback come back.

`reconcile_on_boot` runs the same reconciliation at every API boot (`init_db`).

This module, the rollback mirror and the frozen copy of
`shared.iam.engine_equivalence` are the only readers of `access_role_grants`
(0018 CA2).
"""

from datetime import datetime

from sqlalchemy import Column, and_, inspect, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn

from shared.config import get_settings
from shared.database import Base
from shared import models  # register the complete FK graph (users, access_*)
from shared.access.models import AuthorizationEpoch, PolicyRevision, RoleGrant
from shared.iam import catalog
from shared.iam.models import IamBinding

MARKER = "0014_iam_bindings"
MARKER_0018 = "0018_engine_bindings"
TABLES = [t for t in Base.metadata.sorted_tables if t.name.startswith("iam_")]
_markers = models.AppMigration.__table__
_bindings = IamBinding.__table__
_grants = RoleGrant.__table__
_epoch = AuthorizationEpoch.__table__
_revisions = PolicyRevision.__table__
_audit = models.AdminAudit.__table__
_users = models.User.__table__

# Column -> referred table of its foreign key (None: no foreign key).
COLUMNS_0018 = {
    "permissions": None,
    "condition_ref": "access_policy_revisions",
    "delegation": None,
    "parent_id": "iam_bindings",
}
# The audit action of a revoke through /admin/iam/bindings (shared.iam.bindings).
REVOKE_AUDIT_ACTION = "iam.binding.revoke"
FOREIGN_KEYS_0018 = {
    "condition_ref": "fk_iam_bindings_condition_ref",
    "parent_id": "fk_iam_bindings_parent",
}
INDEX_0018 = "ix_iam_bindings_subject_role"

# Fields a migrated binding carries over unchanged from its grant (CA1), as
# (binding column, grant column). Validity, revocation and version are compared
# as "binding at least as restrictive" (§4.2.3).
_SAME = (
    ("subject_id", "user_id"),
    ("role", "role"),
    ("permissions", "permissions"),
    ("condition_ref", "policy_revision_id"),
    ("delegation", "delegation"),
    ("parent_id", "parent_id"),
    ("granted_by", "granted_by"),
    ("created_at", "created_at"),
)


def _tables(conn):
    return set(inspect(conn).get_table_names())


def _in_transaction(bind, step):
    if isinstance(bind, Engine):
        with bind.begin() as conn:
            return step(conn)
    return step(bind)


def _mark(conn, name):
    if conn.execute(_markers.select().where(_markers.c.name == name)).first() is None:
        conn.execute(_markers.insert().values(name=name, applied_at=datetime.utcnow()))


# -- 0014 -------------------------------------------------------------------------


def _upgrade(conn):
    if "users" not in _tables(conn):
        raise RuntimeError("Apply the base schema before the 0014 IAM migration")
    _markers.create(conn, checkfirst=True)
    Base.metadata.create_all(conn, tables=TABLES)
    for table in TABLES:
        for index in table.indexes:
            index.create(conn, checkfirst=True)
    _mark(conn, MARKER)


def upgrade(bind):
    _in_transaction(bind, _upgrade)


def _foreign_keys(conn):
    """{column: referred table} of the single-column foreign keys of iam_bindings."""
    return {
        fk["constrained_columns"][0]: fk["referred_table"]
        for fk in inspect(conn).get_foreign_keys("iam_bindings")
        if len(fk["constrained_columns"]) == 1
    }


def _validate(conn):
    tables = _tables(conn)
    if not {t.name for t in TABLES}.issubset(tables):
        raise RuntimeError("IAM_MODE requires the explicit 0014 migration")
    columns = {c["name"] for c in inspect(conn).get_columns("iam_bindings")}
    if not set(COLUMNS_0018).issubset(columns):
        raise RuntimeError("This release requires the explicit 0018 IAM migration")
    fks = _foreign_keys(conn)
    if any(fks.get(c) != t for c, t in COLUMNS_0018.items() if t):
        raise RuntimeError("This release requires the 0018 iam_bindings foreign keys")
    # The platform BINDING_EXISTS locking read forces this index on MySQL (§4.3)
    if INDEX_0018 not in {i["name"] for i in inspect(conn).get_indexes("iam_bindings")}:
        raise RuntimeError("This release requires the 0018 iam_bindings index")
    if "access_role_grants" in tables:
        orphan = conn.execute(
            select(_grants.c.id)
            .where(_grants.c.id.notin_(select(_bindings.c.id)))
            .limit(1)
        ).first()
        if orphan is not None:
            raise RuntimeError(
                "access_role_grants has rows without an iam_binding of the same id; "
                "run the 0018 migration (reconciliation)"
            )


def validate_schema(bind):
    """IAM tables, the 0018 columns and foreign keys, and no grant without binding."""
    if isinstance(bind, Engine):
        with bind.connect() as conn:
            _validate(conn)
    else:
        _validate(bind)


def _downgrade(conn):
    if get_settings().iam_mode != "off":
        raise RuntimeError("Set IAM_MODE=off before dropping iam_bindings")
    if "iam_bindings" in _tables(conn):
        foreign = conn.execute(
            select(_bindings.c.id)
            .where(_bindings.c.role.notin_(list(catalog.ROLES)))
            .limit(1)
        ).first()
        if foreign is not None:
            raise RuntimeError(
                "iam_bindings holds bindings outside the platform family; "
                "downgrade the 0018 migration first"
            )
    for table in reversed(TABLES):
        table.drop(conn, checkfirst=True)
    if "app_migrations" in _tables(conn):
        conn.execute(_markers.delete().where(_markers.c.name == MARKER))


def downgrade(bind):
    _in_transaction(bind, _downgrade)


# -- 0018: DDL ----------------------------------------------------------------------


def _ddl_0018(conn):
    tables = _tables(conn)
    if "iam_bindings" not in tables:
        raise RuntimeError("Apply the 0014 IAM migration before 0018")
    if "access_policy_revisions" not in tables:
        raise RuntimeError("Apply the 0009 access migration before 0018")
    sqlite = conn.dialect.name == "sqlite"
    present = {c["name"] for c in inspect(conn).get_columns("iam_bindings")}
    for name, referred in COLUMNS_0018.items():
        if name in present:
            continue
        added = Column(name, _bindings.c[name].type, nullable=True)
        ddl = str(CreateColumn(added).compile(dialect=conn.dialect))
        if referred and sqlite:
            # SQLite cannot add a constraint later: declare it with the column.
            ddl += f" CONSTRAINT {FOREIGN_KEYS_0018[name]} REFERENCES {referred} (id)"
        conn.execute(text(f"ALTER TABLE iam_bindings ADD COLUMN {ddl}"))
    if not sqlite:
        fks = _foreign_keys(conn)
        for name, referred in COLUMNS_0018.items():
            if referred and name not in fks:
                conn.execute(
                    text(
                        f"ALTER TABLE iam_bindings ADD CONSTRAINT {FOREIGN_KEYS_0018[name]} "
                        f"FOREIGN KEY ({name}) REFERENCES {referred} (id)"
                    )
                )
    for index in _bindings.indexes:
        if index.name == INDEX_0018:
            index.create(conn, checkfirst=True)


# -- 0018: copy, reconciliation, validation -----------------------------------------


def _lock_epoch(conn):
    row = conn.execute(
        select(_epoch.c.version).where(_epoch.c.id == 1).with_for_update()
    ).first()
    if row is None:
        raise RuntimeError("0009 authorization epoch is missing")


def _bump_epoch(conn):
    conn.execute(
        _epoch.update().where(_epoch.c.id == 1).values(version=_epoch.c.version + 1)
    )


def _revoked_by(conn, grant_id):
    """
    Who revoked a grant: the last revoke audit row, if that user exists.

    Both the 0009 row (`access.revoked` on `access`) and the IAM one
    (`iam.binding.revoke` on `iam_binding`, CA12) count: `access_role_grants`
    has no `revoked_by`, so after a downgrade/upgrade round trip the audit is
    the only place a binding revoked through the IAM route keeps its revoker.
    """
    actor = conn.execute(
        select(_audit.c.actor_user_id)
        .where(
            _audit.c.target_id == str(grant_id),
            or_(
                and_(_audit.c.action == "access.revoked", _audit.c.target_type == "access"),
                and_(_audit.c.action == REVOKE_AUDIT_ACTION, _audit.c.target_type == "iam_binding"),
            ),
        )
        .order_by(_audit.c.created_at.desc(), _audit.c.id.desc())
        .limit(1)
    ).scalar()
    if actor is None:
        return None
    exists = conn.execute(select(_users.c.id).where(_users.c.id == actor)).first()
    return actor if exists else None


def _binding_values(g, revoked_by, parent_id):
    return dict(
        id=g["id"],
        subject_type="user",
        subject_id=g["user_id"],
        role=g["role"],
        scope_type="platform",
        scope_id=None,
        permissions=g["permissions"],
        condition_ref=g["policy_revision_id"],
        delegation=g["delegation"],
        parent_id=parent_id,
        granted_by=g["granted_by"],
        expires_at=g["expires_at"],
        revoked_at=g["revoked_at"],
        revoked_by=revoked_by,
        version=g["version"],
        created_at=g["created_at"],
    )


def _topological(rows, done):
    """
    `rows` ({id: row}) ordered so that a parent precedes its children.

    `done` holds ids already present on the destination. Returns (ordered,
    cyclic): `cyclic` are rows whose parent chain never reaches a present row —
    a `parent_id` cycle — and must be inserted unlinked, then linked.
    """
    pending = dict(rows)
    done = set(done)
    ordered = []
    while pending:
        ready = sorted(
            (r for r in pending.values() if not r["parent_id"] or r["parent_id"] in done),
            key=lambda r: (r["created_at"] or datetime.min, r["id"]),
        )
        if not ready:
            break
        for r in ready:
            ordered.append(r)
            done.add(r["id"])
            del pending[r["id"]]
    return ordered, sorted(pending.values(), key=lambda r: r["id"])


def _copy_missing(conn) -> int:
    """§4.2.2: every grant without a binding of the same id gets one, parents first."""
    grants = {r["id"]: r for r in conn.execute(select(_grants)).mappings()}
    present = set(conn.execute(select(_bindings.c.id)).scalars())
    missing = {k: v for k, v in grants.items() if k not in present}
    if not missing:
        return 0
    dangling = sorted(
        k for k, v in missing.items()
        if v["parent_id"] and v["parent_id"] not in grants and v["parent_id"] not in present
    )
    if dangling:
        # Copying without the parent would turn a delegated grant into a root one.
        raise RuntimeError(f"access_role_grants rows reference missing parents: {dangling}")
    ordered, cyclic = _topological(missing, present)
    for g in ordered:
        conn.execute(_bindings.insert().values(**_binding_values(g, _revoked_by(conn, g["id"]), g["parent_id"])))
    # A parent_id cycle (only reachable through UPDATEs) is copied as it is: inserted
    # unlinked, then linked, in the same transaction. It never decides "allow":
    # the cycle guard of active_grant denies it on both sides.
    for g in cyclic:
        conn.execute(_bindings.insert().values(**_binding_values(g, _revoked_by(conn, g["id"]), None)))
    for g in cyclic:
        conn.execute(_bindings.update().where(_bindings.c.id == g["id"]).values(parent_id=g["parent_id"]))
    return len(missing)


def _restrict(conn) -> int:
    """§4.2.3 step 2: each binding becomes the most restrictive of itself and its grant."""
    changed = 0
    rows = conn.execute(
        select(
            _bindings.c.id,
            _bindings.c.revoked_at,
            _bindings.c.revoked_by,
            _bindings.c.expires_at,
            _bindings.c.version,
            _grants.c.revoked_at.label("g_revoked_at"),
            _grants.c.expires_at.label("g_expires_at"),
            _grants.c.version.label("g_version"),
        ).join(_grants, _grants.c.id == _bindings.c.id)
    ).mappings().all()
    for r in rows:
        values = {}
        if r["revoked_at"] is None and r["g_revoked_at"] is not None:
            values["revoked_at"] = r["g_revoked_at"]
            values["revoked_by"] = r["revoked_by"] or _revoked_by(conn, r["id"])
        if r["g_expires_at"] < r["expires_at"]:
            values["expires_at"] = r["g_expires_at"]
        if r["g_version"] > r["version"]:
            values["version"] = r["g_version"]
        if values:
            conn.execute(_bindings.update().where(_bindings.c.id == r["id"]).values(**values))
            changed += 1
    return changed


def verify_engine_bindings(conn):
    """
    §4.2.3 step 3 and CA1. Raises RuntimeError listing the problems found.

    - the engines bindings are exactly the grants (same ids, same count); each
      carries its grant's fields and is at least as restrictive (revoked if the
      grant is, expires no later, version no lower);
    - an engines binding has a user subject, non-empty `permissions` within its
      role and a resolvable `condition_ref`;
    - a platform binding has none of the four engines columns.
    """
    problems = []
    grants = (
        {r["id"]: r for r in conn.execute(select(_grants)).mappings()}
        if "access_role_grants" in _tables(conn)
        else {}
    )
    bindings = {r["id"]: r for r in conn.execute(select(_bindings)).mappings()}
    revisions = set(conn.execute(select(_revisions.c.id)).scalars())
    engines = {k for k, b in bindings.items() if b["role"] in catalog.ENGINE_ROLES or k in grants}
    if engines != set(grants):
        problems.append(
            f"engines bindings {len(engines)} != grants {len(grants)}: "
            f"missing {sorted(set(grants) - engines)}, extra {sorted(engines - set(grants))}"
        )
    for k, g in grants.items():
        if g["role"] not in catalog.ENGINE_ROLES:
            # Its binding would fall in neither family: listed and revocable by the
            # platform family without the epoch, dropped silently by the reader.
            problems.append(f"{k}: grant role {g['role']!r} outside the engines family")
        b = bindings.get(k)
        if b is None:
            continue
        if b["subject_type"] != "user" or b["scope_type"] != "platform" or b["scope_id"] is not None:
            problems.append(f"{k}: subject or scope differs")
        for mine, theirs in _SAME:
            if b[mine] != g[theirs]:
                problems.append(f"{k}: {mine} differs from {theirs}")
        if g["revoked_at"] is not None and b["revoked_at"] is None:
            problems.append(f"{k}: revoked grant has an unrevoked binding")
        if b["expires_at"] > g["expires_at"]:
            problems.append(f"{k}: binding outlives its grant")
        if b["version"] < g["version"]:
            problems.append(f"{k}: binding version below its grant")
    for k, b in bindings.items():
        engine_role = catalog.ENGINE_ROLES.get(b["role"])
        if engine_role is not None:
            ps = b["permissions"]
            if b["subject_type"] != "user":
                problems.append(f"{k}: engines binding of a non-user subject")
            if not ps or not set(ps) <= engine_role.permissions:
                problems.append(f"{k}: permissions empty or outside role {b['role']}")
            if not b["condition_ref"] or b["condition_ref"] not in revisions:
                problems.append(f"{k}: condition_ref does not resolve")
        elif b["role"] in catalog.ROLES:
            if any(b[c] is not None for c in COLUMNS_0018):
                problems.append(f"{k}: platform binding carries engines columns")
    if problems:
        raise RuntimeError(
            "0018 engine bindings do not match access_role_grants: " + "; ".join(problems[:20])
        )


def reconcile_engine_grants(conn) -> dict:
    """
    §4.2.3: idempotent and restrictive-only, under the 0009 epoch lock.

    Copies missing grants, restricts bindings to the most restrictive of both
    tables, validates, and bumps the epoch in the same transaction when any row
    changed. A no-op without `access_role_grants`.
    """
    if "access_role_grants" not in _tables(conn):
        return {"copied": 0, "restricted": 0}
    _lock_epoch(conn)
    copied = _copy_missing(conn)
    restricted = _restrict(conn)
    verify_engine_bindings(conn)
    if copied or restricted:
        _bump_epoch(conn)
    return {"copied": copied, "restricted": restricted}


def reconcile_on_boot(bind) -> dict:
    """
    §4.2.3 at API boot (`init_db`): reconcile whenever `access_role_grants` and the
    0018 columns exist, independently of the marker. Skipped before the 0018
    migration (nothing to reconcile into) and on a database without the 0009
    epoch and without grants (a fresh install).
    """
    def step(conn):
        tables = _tables(conn)
        if not {"access_role_grants", "iam_bindings"} <= tables:
            return {"copied": 0, "restricted": 0}
        present = {c["name"] for c in inspect(conn).get_columns("iam_bindings")}
        if not set(COLUMNS_0018) <= present:
            return {"copied": 0, "restricted": 0}
        has_epoch = "access_authorization_epoch" in tables and conn.execute(
            select(_epoch.c.id).where(_epoch.c.id == 1)
        ).first() is not None
        if not has_epoch:
            if conn.execute(select(_grants.c.id).limit(1)).first() is not None:
                raise RuntimeError("0009 authorization epoch is missing")
            return {"copied": 0, "restricted": 0}
        return reconcile_engine_grants(conn)

    return _in_transaction(bind, step)


def _data_0018(conn):
    _markers.create(conn, checkfirst=True)
    reconcile_engine_grants(conn)
    _mark(conn, MARKER_0018)


def upgrade_0018(bind):
    """DDL, then copy + reconciliation + validation + marker in a transaction of its own."""
    _in_transaction(bind, _ddl_0018)
    _in_transaction(bind, _data_0018)


# -- 0018: downgrade ----------------------------------------------------------------


def _grant_values(b, parent_id):
    return dict(
        id=b["id"],
        user_id=b["subject_id"],
        role=b["role"],
        permissions=b["permissions"],
        policy_revision_id=b["condition_ref"],
        delegation=b["delegation"],
        parent_id=parent_id,
        granted_by=b["granted_by"],
        expires_at=b["expires_at"],
        revoked_at=b["revoked_at"],
        version=b["version"],
        created_at=b["created_at"],
    )


def _mirror_back(conn):
    """
    Downgrade step 1 (§4.2.1): for every engines id, `access_role_grants` gets the
    most restrictive of both tables, and every engines binding it lacks. Refuses
    when a binding cannot be represented as a 0009 grant.
    """
    grants = {r["id"]: r for r in conn.execute(select(_grants)).mappings()}
    engines = {
        r["id"]: r
        for r in conn.execute(select(_bindings)).mappings()
        if r["role"] in catalog.ENGINE_ROLES or r["id"] in grants
    }
    bad = sorted(
        k for k, b in engines.items()
        if k not in grants and (
            b["subject_type"] != "user"
            or not b["permissions"]
            or not b["condition_ref"]
            or (b["parent_id"] and b["parent_id"] not in engines and b["parent_id"] not in grants)
        )
    )
    if bad:
        raise RuntimeError(f"engines bindings cannot be mirrored into access_role_grants: {bad}")
    changed = 0
    for k, b in engines.items():
        g = grants.get(k)
        if g is None:
            continue
        values = {}
        if b["revoked_at"] is not None and (g["revoked_at"] is None or b["revoked_at"] < g["revoked_at"]):
            values["revoked_at"] = b["revoked_at"]
        if b["expires_at"] < g["expires_at"]:
            values["expires_at"] = b["expires_at"]
        if b["version"] > g["version"]:
            values["version"] = b["version"]
        if values:
            conn.execute(_grants.update().where(_grants.c.id == k).values(**values))
            changed += 1
    missing = {k: b for k, b in engines.items() if k not in grants}
    ordered, cyclic = _topological(missing, set(grants))
    for b in ordered:
        conn.execute(_grants.insert().values(**_grant_values(b, b["parent_id"])))
    for b in cyclic:
        conn.execute(_grants.insert().values(**_grant_values(b, None)))
    for b in cyclic:
        conn.execute(_grants.update().where(_grants.c.id == b["id"]).values(parent_id=b["parent_id"]))
    return changed + len(missing), set(engines)


def _downgrade_data_0018(conn):
    if "access_role_grants" in _tables(conn):
        _lock_epoch(conn)
        changed, engines = _mirror_back(conn)
    else:
        engines = {
            r["id"]
            for r in conn.execute(select(_bindings.c.id, _bindings.c.role)).mappings()
            if r["role"] in catalog.ENGINE_ROLES
        }
        if engines:
            raise RuntimeError("engines bindings exist but access_role_grants does not")
        changed = 0
    if engines:
        ids = sorted(engines)
        conn.execute(_bindings.update().where(_bindings.c.id.in_(ids)).values(parent_id=None))
        conn.execute(_bindings.delete().where(_bindings.c.id.in_(ids)))
    if changed:
        _bump_epoch(conn)
    if "app_migrations" in _tables(conn):
        conn.execute(_markers.delete().where(_markers.c.name == MARKER_0018))


def _drop_columns_0018(conn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    present = {c["name"] for c in inspect(conn).get_columns("iam_bindings")}
    columns = [c for c in COLUMNS_0018 if c in present]
    indexes = {i["name"] for i in inspect(conn).get_indexes("iam_bindings")}
    ops = Operations(MigrationContext.configure(conn))
    if conn.dialect.name == "sqlite":
        # SQLite cannot drop a constrained column: batch mode rebuilds the table
        # without the dropped columns and their constraints.
        if columns or INDEX_0018 in indexes:
            with ops.batch_alter_table("iam_bindings", recreate="always") as batch:
                if INDEX_0018 in indexes:
                    batch.drop_index(INDEX_0018)
                for c in columns:
                    batch.drop_column(c)
        return
    for fk in inspect(conn).get_foreign_keys("iam_bindings"):
        if fk["name"] and fk["constrained_columns"][:1] in (["condition_ref"], ["parent_id"]):
            ops.drop_constraint(fk["name"], "iam_bindings", type_="foreignkey")
    if INDEX_0018 in indexes:
        ops.drop_index(INDEX_0018, table_name="iam_bindings")
    for c in columns:
        ops.drop_column("iam_bindings", c)


def downgrade_0018(bind):
    """Mirror back restrictively, delete the engines bindings and the marker, drop the columns."""
    if "iam_bindings" not in _tables(bind):
        return
    present = {c["name"] for c in inspect(bind).get_columns("iam_bindings")}
    if set(COLUMNS_0018) <= present:
        _in_transaction(bind, _downgrade_data_0018)
    _in_transaction(bind, _drop_columns_0018)
