"""
Rollback mirror of the engines family into `access_role_grants` (spec 0018 CA9).

Every grant and revocation of an engines binding is copied, by id and in the same
transaction, into `access_role_grants`, so that the pre-0018 code — which reads
only that table — never sees more access than the bindings grant after a
rollback. A failure here propagates and aborts the transaction.

Write-only by id: it never reads `access_role_grants` (0018 CA2). It updates the
row of the same id and inserts it when the update touched nothing.
"""

from sqlalchemy.orm import Session

from shared.access.models import RoleGrant
from shared.iam.models import IamBinding

_grants = RoleGrant.__table__


def _values(b: IamBinding) -> dict:
    return dict(
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


def mirror(db: Session, b: IamBinding) -> None:
    """Write `b` (an engines binding, already flushed) over the grant of the same id."""
    if b.subject_type != "user" or not b.permissions or not b.condition_ref:
        # Not representable as a 0009 grant (only reachable by direct SQL; the
        # write service never creates one): carry over only what restricts.
        db.execute(
            _grants.update()
            .where(_grants.c.id == b.id)
            .values(revoked_at=b.revoked_at, expires_at=b.expires_at, version=b.version)
        )
        return
    values = _values(b)
    updated = db.execute(_grants.update().where(_grants.c.id == b.id).values(**values)).rowcount
    if not updated:
        db.execute(_grants.insert().values(id=b.id, **values))
