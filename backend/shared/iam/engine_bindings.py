"""
The 0009 grants read from `iam_bindings` (spec 0018 §4.3).

A thin adapter, not a second rule set: it returns objects with the interface the
rest of 0009 consumes from a `RoleGrant` (`.id`, `.user_id`, `.role`,
`.permissions`, `.policy_revision_id`, `.delegation`, `.parent_id`,
`.expires_at`, `.revoked_at`, `.version`, `.created_at`), and `grants` /
`active_grant` keep the 0009 semantics: every active grant of the actor counts,
the parent chain is walked with the owner-active check and a cycle guard, and
`lock=True` takes the same row locks.

It only ever sees the `engines` family: `subject_type='user'` and a role of
`catalog.ENGINE_ROLES`. As defense in depth (0018 §4.1) it drops, with a warning,
an engines binding whose `permissions` is NULL/empty, whose `condition_ref` is NULL
or names no policy revision, or whose subject is not a user. A missing condition
is never read as unrestricted.

It never reads `access_role_grants` (0018 CA2): only the frozen copy of
`shared.iam.engine_equivalence` and the migration do.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from shared.access.models import PolicyRevision
from shared.iam import catalog
from shared.iam.models import IamBinding
from shared.models import User

logger = logging.getLogger(__name__)

ENGINE_ROLE_KEYS = tuple(catalog.ENGINE_ROLES)


@dataclass(frozen=True)
class EngineGrant:
    """A `RoleGrant`-shaped view of an engines binding."""

    id: str
    user_id: str
    role: str
    permissions: List[str]
    policy_revision_id: str
    delegation: Optional[Any]
    parent_id: Optional[str]
    granted_by: str
    expires_at: datetime
    revoked_at: Optional[datetime]
    version: int
    created_at: Optional[datetime]


def as_grant(b: IamBinding) -> EngineGrant:
    return EngineGrant(
        id=b.id,
        user_id=b.subject_id,
        role=b.role,
        permissions=list(b.permissions or []),
        policy_revision_id=b.condition_ref,
        delegation=b.delegation,
        parent_id=b.parent_id,
        granted_by=b.granted_by,
        expires_at=b.expires_at,
        revoked_at=b.revoked_at,
        version=b.version,
        created_at=b.created_at,
    )


def well_formed(db, b: IamBinding) -> bool:
    """An engines binding the 0009 decision may use at all (0018 §4.1)."""
    problem = None
    if b.role not in catalog.ENGINE_ROLES:
        problem = "role outside the engines family"
    elif b.subject_type != "user":
        problem = "subject is not a user"
    elif not b.permissions:
        problem = "permissions missing"
    elif not b.condition_ref or db.get(PolicyRevision, b.condition_ref) is None:
        problem = "condition missing"
    if problem:
        logger.warning("Ignoring engines binding %s: %s", b.id, problem)
        return False
    return True


def _engine_rows(db):
    return db.query(IamBinding).filter(
        IamBinding.subject_type == "user",
        IamBinding.role.in_(ENGINE_ROLE_KEYS),
    )


def active_grant(db, grant, seen=None, lock=False) -> bool:
    """0009 `active_grant` over `iam_bindings`: the whole parent chain is active."""
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
        q = _engine_rows(db).filter(IamBinding.id == grant.parent_id).populate_existing()
        parent = (q.with_for_update() if lock else q).first()
        if parent is None or not well_formed(db, parent):
            return False
        return active_grant(db, as_grant(parent), seen, lock)
    return True


def grants(db, actor, lock=False) -> List[EngineGrant]:
    """Every active engines grant of `actor`, ranked by (created_at, id)."""
    q = (
        _engine_rows(db)
        .filter(IamBinding.subject_id == str(actor))
        .order_by(IamBinding.created_at, IamBinding.id)
        .populate_existing()
    )
    if lock:
        q = q.with_for_update()
    rows = [as_grant(b) for b in q if well_formed(db, b)]
    return [g for g in rows if active_grant(db, g, lock=lock)]
