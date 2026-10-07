"""
Offline equivalence of the 0009 engine decisions, legacy store vs IAM store
(spec 0018 CA4).

- **legacy**: `policy.grants` / `policy.active_grant` as they stood before 0018,
  reading `access_role_grants`, kept below as a **frozen copy**. It must not import
  the code under comparison (`shared.iam.engine_bindings`): comparing a module with
  itself proves nothing. Together with the 0018 migration and the rollback mirror,
  this is the only reader of `access_role_grants`.
- **iam**: the grants reader over `iam_bindings` handed to `run` (the CLI passes
  `shared.iam.engine_bindings.grants`).

Each side is installed in turn as `shared.access.policy.grants`, and the very same
decision code runs on top of it: `policy.authorize` over a request matrix (actor ×
permission × engine / feature / profile / runtime / resources), `navigation`,
`visible_catalog`, `scoped_query` and `service._delegator`. Any difference is a
divergence and a gate failure: the migration is not deployed until a run against
the dev snapshot is clean. The CLI is `scripts/iam_engine_equivalence.py`; CI runs
`run()` against the SQLite fixtures of `tests/test_iam_engine_equivalence.py`.

Order: the 0009 query has no ORDER BY, so which of several satisfying grants
`authorize` reports was never part of its contract. Both sides are ranked by
(created_at, id) so that the reported `grant_id` is comparable.

The decision code runs with engine access enabled (`policy.enabled` forced on) so
that grants are actually consulted; bootstrap users are compared like anyone else.
"""

import argparse
import contextlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.access.models import (
    ExecutionProfile,
    PolicyRevision,
    ResourceScope,
    RoleGrant,
)
from shared.models import Engine, User

GrantsReader = Callable[..., List[Any]]


# -- frozen copy: shared/access/policy.py before spec 0018 ---------------------------


def legacy_active_grant(db, grant, seen=None, lock=False):
    seen = set() if seen is None else seen
    if (
        not grant
        or grant.id in seen
        or grant.revoked_at
        or grant.expires_at <= datetime.utcnow()
    ):
        return False
    seen.add(grant.id)
    q = db.query(User).filter_by(id=grant.user_id).populate_existing()
    owner = (q.with_for_update() if lock else q).first()
    if not owner or not owner.is_active:
        return False
    if grant.parent_id:
        q = db.query(RoleGrant).filter_by(id=grant.parent_id).populate_existing()
        parent = (q.with_for_update() if lock else q).first()
        return legacy_active_grant(db, parent, seen, lock)
    return True


def legacy_grants(db, actor, lock=False):
    q = db.query(RoleGrant).filter_by(user_id=str(actor)).populate_existing()
    if lock:
        q = q.with_for_update()
    return [g for g in q if legacy_active_grant(db, g, lock=lock)]


# -- harness -------------------------------------------------------------------------


def _ranked(reader: GrantsReader) -> GrantsReader:
    def grants(db, actor, lock=False):
        return sorted(
            reader(db, actor, lock=lock),
            key=lambda g: (g.created_at or datetime.min, g.id),
        )

    return grants


@contextlib.contextmanager
def _source(reader: GrantsReader):
    """Install `reader` as `policy.grants`, with engine access on."""
    from shared.access import policy

    saved = policy.grants, policy.enabled
    policy.grants, policy.enabled = _ranked(reader), (lambda: True)
    try:
        yield
    finally:
        policy.grants, policy.enabled = saved


@dataclass
class Matrix:
    """What is asked of each actor. `from_db` derives a default from the database."""

    permissions: List[str]
    engines: List[Engine]
    features: List[Optional[str]]
    profiles: List[ExecutionProfile]
    runtimes: List[Dict[str, Any]]
    resources: List[List[str]]
    max_usd: List[Optional[str]]
    catalog_rows: Dict[str, List[dict]]
    constraints: List[dict]

    @classmethod
    def from_db(cls, db: Session) -> "Matrix":
        from shared.access import policy

        revisions = [r.constraints for r in db.query(PolicyRevision).order_by(PolicyRevision.id)]
        features = sorted({f for c in revisions for f in c.get("features") or []})
        adapters = sorted(
            {e.adapter_type for e in db.query(Engine)}
            | {a for c in revisions for a in c.get("adapters") or []}
        )
        hosts = sorted({h for c in revisions for h in c.get("host_ids") or []})
        models = sorted({m for c in revisions for m in c.get("model_ids") or []})
        runtimes = [None] + [
            dict(binding={"workers": 1, "executions_per_worker": 1, "cpu": 1},
                 max_replicas=1, memory_mb=256, model_profile_id=m)
            for m in models
        ]
        return cls(
            permissions=sorted(policy.PERMISSIONS),
            engines=db.query(Engine).order_by(Engine.id).all(),
            features=[None] + features,
            profiles=db.query(ExecutionProfile).order_by(ExecutionProfile.id).all(),
            runtimes=runtimes,
            resources=[[s.key] for s in db.query(ResourceScope).order_by(ResourceScope.key)],
            max_usd=[None, "0.01", "1000"],
            catalog_rows={
                "adapter": [dict(type=a, features=features) for a in adapters],
                "host": [dict(id=h) for h in hosts],
                "model": [dict(id=m, feature=f, adapters=adapters) for m in models for f in features],
            },
            constraints=revisions,
        )


@dataclass
class Divergence:
    actor: str
    check: str
    request: str
    legacy: Any
    iam: Any

    def __str__(self):
        return f"{self.actor} {self.check} {self.request}: legacy={self.legacy!r} iam={self.iam!r}"


@dataclass
class Report:
    decisions: int = 0
    divergences: List[Divergence] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.divergences


def _outcome(call):
    from shared.engine_control.service import ControlError

    try:
        return ("allow", call())
    except ControlError as exc:
        return ("deny", exc.code, exc.status)
    except Exception as exc:  # a crash is an outcome too, and must match
        return ("error", type(exc).__name__)


def _requests(m: Matrix):
    """(label, kwargs) of every authorize request of the matrix."""
    for permission in m.permissions:
        yield (permission, "-"), dict(permission=permission)
        for e in m.engines:
            for f in m.features:
                yield (permission, e.id, f), dict(permission=permission, engine=e, feature=f)
            for rt in m.runtimes:
                for usd in m.max_usd:
                    yield (permission, e.id, "runtime", (rt or {}).get("model_profile_id"), usd), dict(
                        permission=permission, engine=e, runtime=rt, max_usd=usd
                    )
            for keys in m.resources:
                yield (permission, e.id, "resources", tuple(keys)), dict(
                    permission=permission, engine=e, resources=keys
                )
        for p in m.profiles:
            for creating in (False, True):
                yield (permission, "profile", p.id, creating), dict(
                    permission=permission, profile=p, creating=creating
                )


def _decisions(db: Session, actor: User, m: Matrix, delegations: Sequence[tuple]) -> Dict[tuple, Any]:
    from shared.access import policy, service
    from shared.access.models import ExecutionProfile as Profile
    from shared.engine_control.models import EngineOperation

    out: Dict[tuple, Any] = {}
    out[("navigation",)] = _outcome(lambda: policy.navigation(db, actor))
    for label, kw in _requests(m):
        permission = kw.pop("permission")
        out[("authorize",) + label] = _outcome(
            lambda: policy.authorize(db, actor.id, permission, force=True, **kw)
        )
    for kind, rows in m.catalog_rows.items():
        out[("visible_catalog", kind)] = _outcome(lambda: policy.visible_catalog(db, actor.id, rows, kind))
    for kind, model in (("engine", Engine), ("profile", Profile), ("operation", EngineOperation)):
        out[("scoped_query", kind)] = _outcome(
            lambda: sorted(r[0] for r in policy.scoped_query(db, actor.id, db.query(model.id), kind))
        )
    expiry = datetime.utcnow() + timedelta(seconds=60)
    for i, (permissions, constraints, delegation) in enumerate(delegations):
        out[("_delegator", i)] = _outcome(
            lambda: service._delegator(db, actor.id, permissions, constraints, expiry, delegation)
        )
    db.rollback()
    return out


def _delegation_requests(db: Session, m: Matrix) -> List[tuple]:
    """Every (role permissions × condition) plus every legacy grant as `list_grants` asks."""
    from shared.access import policy

    asks = [
        (sorted(perms), c, None)
        for perms in policy.ROLES.values()
        for c in m.constraints
    ]
    revisions = {r.id: r.constraints for r in db.query(PolicyRevision)}
    for g in db.query(RoleGrant).order_by(RoleGrant.id):
        c = revisions.get(g.policy_revision_id)
        if c is not None:
            asks.append((list(g.permissions), c, g.delegation))
    return asks


def run(
    session_factory: Callable[[], Session],
    iam_grants: GrantsReader,
    *,
    user_ids: Optional[Iterable[str]] = None,
    matrix: Optional[Matrix] = None,
) -> Report:
    report = Report()
    with session_factory() as db:
        users = db.query(User).order_by(User.id)
        if user_ids:
            users = users.filter(User.id.in_(list(user_ids)))
        ids = [u.id for u in users]
        m = matrix or Matrix.from_db(db)
        delegations = _delegation_requests(db, m)
    for uid in ids:
        sides = {}
        for name, reader in (("legacy", legacy_grants), ("iam", iam_grants)):
            with session_factory() as db, _source(reader):
                actor = db.get(User, uid)
                m_local = matrix or Matrix.from_db(db)
                sides[name] = _decisions(db, actor, m_local, delegations)
        for key, legacy in sides["legacy"].items():
            report.decisions += 1
            iam = sides["iam"].get(key)
            if legacy != iam:
                report.divergences.append(Divergence(uid, key[0], repr(key[1:]), legacy, iam))
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare the 0009 engine decisions over access_role_grants and iam_bindings (spec 0018 CA4)."
    )
    parser.add_argument("--db-url", help="Database URL (default: DATABASE_URL of the settings)")
    parser.add_argument("--user", action="append", default=[], help="Only these user ids (repeatable)")
    args = parser.parse_args(argv)
    try:
        from shared.config import get_settings
        from shared.iam.engine_bindings import grants as iam_grants

        engine = create_engine(args.db_url or get_settings().database_url)
        factory = sessionmaker(bind=engine)
        report = run(factory, iam_grants, user_ids=args.user or None)
    except Exception as exc:  # pragma: no cover - operator-facing
        print(f"could not run: {exc}", file=sys.stderr)
        return 2
    for d in report.divergences:
        print(d)
    print(f"{report.decisions} decisions, {len(report.divergences)} divergences")
    return 0 if report.clean else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
