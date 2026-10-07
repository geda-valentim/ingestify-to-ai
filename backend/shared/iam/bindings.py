"""
Granting and revoking platform bindings (spec 0014 §4.8, §4.9, CA7).

Rules:
- the actor holds `iam.bindings.manage` (bootstrap or a binding);
- nobody grants to themselves (0013 §4 rule 6);
- nobody grants a role holding a permission they do not hold themselves;
- `expires_at` is required, in the future and at most 365 days away (UTC);
- revoking takes `version` (optimistic locking) and is effective on the next
  request, since bindings are never cached across requests;
- every grant and revoke writes an `AdminAudit` row in the same transaction.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from shared.iam import catalog
from shared.iam.decide import Decider, Principal, as_principal
from shared.iam.models import SUBJECT_TYPES, IamBinding
from shared.models import AdminAudit, User

MAX_PLATFORM_TTL = timedelta(days=365)


class IamError(Exception):
    """A refused IAM write: `code` is machine-readable, `status` the HTTP status."""

    def __init__(self, code: str, status: int, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.status = status
        self.detail = detail or code


def to_utc_naive(value) -> datetime:
    """An aware datetime converted to UTC; a naive one is taken as already UTC."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise IamError("INVALID_EXPIRES_AT", 422, "expires_at is not an ISO-8601 datetime") from None
    if not isinstance(value, datetime):
        raise IamError("INVALID_EXPIRES_AT", 422, "expires_at is required")
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def view(b: IamBinding, now: Optional[datetime] = None) -> dict:
    now = now or datetime.utcnow()
    return dict(
        id=b.id,
        subject_type=b.subject_type,
        subject_id=b.subject_id,
        role=b.role,
        scope_type=b.scope_type,
        scope_id=b.scope_id,
        granted_by=b.granted_by,
        expires_at=b.expires_at.isoformat() if b.expires_at else None,
        revoked_at=b.revoked_at.isoformat() if b.revoked_at else None,
        revoked_by=b.revoked_by,
        version=b.version,
        created_at=b.created_at.isoformat() if b.created_at else None,
        active=b.revoked_at is None and b.expires_at > now,
    )


def _audit(db, actor: Principal, action: str, b: IamBinding, before, after, ip):
    db.add(
        AdminAudit(
            actor_user_id=actor.subject_id,
            auth_method="cli" if actor.credential == "cli" else "jwt",
            ip=ip,
            action=action,
            target_type="iam_binding",
            target_id=b.id,
            before=before,
            after=after,
        )
    )


def _require_manager(decider: Decider, actor, permission: str, *, writes: bool = False) -> Principal:
    principal = as_principal(actor)
    decision = decider.decide(principal, permission)
    if not decision.allow:
        raise IamError("ACCESS_DENIED", decision.status)
    # granted_by / revoked_by are users.id FKs (§4.8): only a user writes bindings.
    if writes and principal.subject_type != "user":
        raise IamError("ACCESS_DENIED", 403, "Only a user grants or revokes bindings")
    return principal


def _lock_subject(db: Session, subject_type: str, subject_id: str) -> bool:
    """
    Whether the subject exists, locking its row (FOR UPDATE) until the grant
    commits: two concurrent grants for the same subject serialize here, so the
    second one sees the first binding and gets BINDING_EXISTS.
    """
    if subject_type == "user":
        model = User
    else:
        from shared.access.models import ServicePrincipal as model
    row = db.query(model).filter(model.id == subject_id).populate_existing().with_for_update().first()
    if row is None:
        return False
    return subject_type == "user" or row.active is True


def grant(
    db: Session,
    actor,
    *,
    subject_type: str,
    subject_id: str,
    role: str,
    expires_at,
    ip: Optional[str] = None,
    decider: Optional[Decider] = None,
) -> IamBinding:
    decider = decider or Decider(db)
    principal = _require_manager(decider, actor, "iam.bindings.manage", writes=True)
    now = decider.now()

    managed = catalog.ROLES.get(role)
    if managed is None:
        raise IamError("UNKNOWN_ROLE", 422, f"Unknown role {role!r}")
    if subject_type not in SUBJECT_TYPES:
        raise IamError("INVALID_SUBJECT", 422, f"Unknown subject_type {subject_type!r}")
    subject_id = str(subject_id or "").strip()
    if not subject_id:
        raise IamError("INVALID_SUBJECT", 422, "subject_id is required")
    if subject_type == principal.subject_type and subject_id == principal.subject_id:
        raise IamError("SELF_GRANT", 422, "Nobody grants a role to themselves")
    if not _lock_subject(db, subject_type, subject_id):
        raise IamError("SUBJECT_NOT_FOUND", 422, "The subject does not exist")

    held = decider.platform_permissions(principal)
    missing = sorted(managed.permissions - held)
    if missing:
        raise IamError(
            "ROLE_ABOVE_GRANTOR", 422,
            f"The role holds permissions the grantor does not: {', '.join(missing)}",
        )

    expires = to_utc_naive(expires_at)
    if expires <= now:
        raise IamError("INVALID_EXPIRES_AT", 422, "expires_at must be in the future")
    if expires > now + MAX_PLATFORM_TTL:
        raise IamError("INVALID_EXPIRES_AT", 422, "Platform bindings last at most 365 days")

    existing = (
        db.query(IamBinding)
        .filter(
            IamBinding.subject_type == subject_type,
            IamBinding.subject_id == subject_id,
            IamBinding.role == role,
            IamBinding.scope_type == "platform",
            IamBinding.revoked_at.is_(None),
            IamBinding.expires_at > now,
        )
        # A locking read sees the latest commit, not this transaction's snapshot.
        .with_for_update()
        .first()
    )
    if existing is not None:
        raise IamError("BINDING_EXISTS", 409, f"An active binding exists: {existing.id}")

    b = IamBinding(
        subject_type=subject_type,
        subject_id=subject_id,
        role=role,
        scope_type="platform",
        scope_id=None,
        granted_by=principal.subject_id,
        expires_at=expires,
        version=0,
        created_at=now,
    )
    db.add(b)
    db.flush()
    _audit(db, principal, "iam.binding.grant", b, None, view(b, now), ip)
    db.commit()
    return b


def revoke(
    db: Session,
    actor,
    binding_id: str,
    *,
    version: int,
    ip: Optional[str] = None,
    decider: Optional[Decider] = None,
) -> IamBinding:
    decider = decider or Decider(db)
    principal = _require_manager(decider, actor, "iam.bindings.manage", writes=True)
    now = decider.now()

    b = db.get(IamBinding, str(binding_id))
    if b is None:
        raise IamError("BINDING_NOT_FOUND", 404)
    if b.revoked_at is not None:
        raise IamError("ALREADY_REVOKED", 409)
    if b.version != version:
        raise IamError("VERSION_CONFLICT", 409, f"Binding is at version {b.version}, not {version}; re-read it")
    before = view(b, now)

    # Conditional on the version read: a concurrent revoke loses with 409.
    updated = (
        db.query(IamBinding)
        .filter(
            IamBinding.id == b.id,
            IamBinding.version == version,
            IamBinding.revoked_at.is_(None),
        )
        .update(
            {
                IamBinding.revoked_at: now,
                IamBinding.revoked_by: principal.subject_id,
                IamBinding.version: version + 1,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        raise IamError("VERSION_CONFLICT", 409, "Binding changed; re-read it")
    db.refresh(b)
    _audit(db, principal, "iam.binding.revoke", b, before, view(b, now), ip)
    db.commit()
    return b


def list_bindings(db: Session, actor, *, include_inactive: bool = False, decider: Optional[Decider] = None):
    decider = decider or Decider(db)
    _require_manager(decider, actor, "iam.bindings.read")
    now = decider.now()
    q = db.query(IamBinding).filter(IamBinding.scope_type == "platform")
    if not include_inactive:
        q = q.filter(IamBinding.revoked_at.is_(None), IamBinding.expires_at > now)
    return [view(b, now) for b in q.order_by(IamBinding.created_at.desc(), IamBinding.id).all()]
