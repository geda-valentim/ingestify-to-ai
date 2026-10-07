"""
Granting and revoking IAM bindings: the single write service of both role
families (spec 0014 §4.8, §4.9, CA7; spec 0018 §4.3).

Each write branches on the role family before any check, and the families never
cross (0018 §2):

- `platform` (`grant`, `revoke`, `list_bindings`): the 0014 rules below, unchanged;
- `engines` (`grant_engine`, `revoke_engine`, `list_engine_grants`): the 0009
  rules of `create_grant` / `revoke` / `list_grants` over `iam_bindings` — see the
  engines section below.

`grant_binding`, `revoke_binding` and `list_all` (end of the module) serve the
unified `/admin/iam/bindings*` and pick the family first; the deprecated
`/admin/access/grants*` call the engines functions directly. Both families audit
on `target_type="iam_binding"` (`iam.binding.grant` / `iam.binding.revoke`, 0018
CA12).

Platform rules:
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
# CA12: one audit vocabulary for both families (target_type="iam_binding").
GRANT_AUDIT_ACTION = "iam.binding.grant"
REVOKE_AUDIT_ACTION = "iam.binding.revoke"
# The BINDING_EXISTS locking read is pinned to it (0018 §4.3); see migration.INDEX_0018
INDEX_SUBJECT_ROLE = "ix_iam_bindings_subject_role"


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


def view(b: IamBinding, now: Optional[datetime] = None, *, active: Optional[bool] = None) -> dict:
    """
    A binding as the API answers it. `active` is the row's own state (not
    revoked, not expired) unless the caller passes the whole decision: for an
    engines binding, `view_any` also walks the parent chain and the owner.
    """
    now = now or datetime.utcnow()
    own = b.revoked_at is None and b.expires_at > now
    return dict(
        id=b.id,
        family=catalog.ENGINES_FAMILY if _engines(b) else catalog.PLATFORM_FAMILY,
        subject_type=b.subject_type,
        subject_id=b.subject_id,
        role=b.role,
        scope_type=b.scope_type,
        scope_id=b.scope_id,
        permissions=list(b.permissions) if b.permissions is not None else None,
        condition_ref=b.condition_ref,
        delegation=b.delegation,
        parent_id=b.parent_id,
        granted_by=b.granted_by,
        expires_at=b.expires_at.isoformat() if b.expires_at else None,
        revoked_at=b.revoked_at.isoformat() if b.revoked_at else None,
        revoked_by=b.revoked_by,
        version=b.version,
        created_at=b.created_at.isoformat() if b.created_at else None,
        active=own if active is None else (own and active),
    )


def _engines(b: IamBinding) -> bool:
    """
    An engines binding (spec 0018): an engines role, or a copied 0009 grant —
    which always carries `condition_ref` (NOT NULL in access_role_grants), even
    when its role has left `ENGINE_ROLES`. Never the platform family's to list
    or revoke: its revocation goes with the 0009 epoch.
    """
    return catalog.family(b.role) == catalog.ENGINES_FAMILY or b.condition_ref is not None


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

    existing = _active_platform_binding(db, subject_type, subject_id, role, now).first()
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
    _audit(db, principal, GRANT_AUDIT_ACTION, b, None, view(b, now), ip)
    db.commit()
    return b


def _active_platform_binding(db: Session, subject_type: str, subject_id: str, role: str, now):
    """The locking read behind BINDING_EXISTS; `role` is already a platform role."""
    return (
        db.query(IamBinding)
        .filter(
            IamBinding.subject_type == subject_type,
            IamBinding.subject_id == subject_id,
            IamBinding.role == role,
            IamBinding.scope_type == "platform",
            IamBinding.revoked_at.is_(None),
            IamBinding.expires_at > now,
        )
        # Lock order of 0018 §4.3: pinning the (subject_type, subject_id, role)
        # index keeps this locking read on that platform role's rows. Through
        # ix_iam_bindings_subject InnoDB would lock every active binding of the
        # subject, engines ones included, which an effect admission may already
        # hold while it waits on this subject's users row (deadlock).
        .with_hint(IamBinding, f"FORCE INDEX ({INDEX_SUBJECT_ROLE})", "mysql")
        # A locking read sees the latest commit, not this transaction's snapshot.
        .with_for_update()
    )


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
    # Engines bindings (spec 0018) are not this family's to see or revoke.
    if b is None or _engines(b):
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
    _audit(db, principal, REVOKE_AUDIT_ACTION, b, before, view(b, now), ip)
    db.commit()
    return b


def list_bindings(db: Session, actor, *, include_inactive: bool = False, decider: Optional[Decider] = None):
    decider = decider or Decider(db)
    _require_manager(decider, actor, "iam.bindings.read")
    now = decider.now()
    return [view(b, now) for b in _platform_bindings(db, include_inactive, now)]


def _platform_bindings(db: Session, include_inactive: bool, now: datetime):
    q = db.query(IamBinding).filter(
        IamBinding.scope_type == "platform",
        # Engines bindings (spec 0018) are never listed to the platform family.
        IamBinding.role.notin_(list(catalog.ENGINE_ROLES)),
        IamBinding.condition_ref.is_(None),
    )
    if not include_inactive:
        q = q.filter(IamBinding.revoked_at.is_(None), IamBinding.expires_at > now)
    return q.order_by(IamBinding.created_at.desc(), IamBinding.id).all()


# -- engines family (spec 0018 §4.3, CA5, CA7, CA9, CA17) ----------------------------
#
# The 0009 grant rules, now over `iam_bindings`: bootstrap or `access.grants.manage`
# plus a covering delegation envelope (`shared.access.service._delegator`); a
# materialized, non-empty `permissions` within the role; a mandatory condition
# (`condition_ref`, a policy revision); `delegation` for `access_admin` only;
# several active bindings of the same role per user are valid. No BINDING_EXISTS
# and no ROLE_ABOVE_GRANTOR: the limit is the envelope. Self-grants are refused
# (0013 §4 rule 6, an intentional deviation from 0009).
#
# Lock order: the 0009 epoch (FOR UPDATE) before reading or changing any binding
# or user, then `users`, then `iam_bindings` / `access_role_grants`. Every write
# bumps the epoch and is mirrored into `access_role_grants` in the same
# transaction (`shared.iam.engine_mirror`), so a rollback never widens access.
#
# Errors are `ControlError`s with the 0009 codes, as `/admin/access/grants`
# answers them; the unified route converts them to `IamError` (`_engines_refused`).


def _control_error(code, status=409):
    from shared.engine_control.service import ControlError

    return ControlError(code, status)


def _engine_query(db: Session):
    return db.query(IamBinding).filter(
        IamBinding.subject_type == "user",
        IamBinding.role.in_(list(catalog.ENGINE_ROLES)),
    )


def _covered(db: Session, actor: str, b: IamBinding) -> None:
    """`_delegator` covers binding `b`, as 0009 checked before listing or revoking."""
    from shared.access import service as access
    from shared.access.models import PolicyRevision
    from shared.admin import is_effective_admin

    if is_effective_admin(db.get(User, actor)):
        return
    revision = db.get(PolicyRevision, b.condition_ref) if b.condition_ref else None
    if revision is None or not b.permissions:
        # A malformed binding is never covered by an envelope; bootstrap only.
        raise _control_error("DELEGATION_EXCEEDED", 403)
    access._delegator(
        db,
        actor,
        b.permissions,
        revision.constraints,
        min(b.expires_at, datetime.utcnow() + timedelta(seconds=60)),
        b.delegation,
    )


def _engine_audit(db: Session, actor: str, action: str, b: IamBinding, before, after, ip=None):
    """
    CA12: the same `iam_binding` audit target as the platform family, carrying
    what 0009 recorded on `access` (subject, role, policy revision = condition,
    parent) in `before` / `after`. The 0009 rows already written stay intact.
    """
    db.add(
        AdminAudit(
            actor_user_id=str(actor),
            auth_method="jwt",
            ip=ip,
            action=action,
            target_type="iam_binding",
            target_id=b.id,
            before=before,
            after=after,
        )
    )


def grant_engine(
    db: Session,
    actor: str,
    *,
    subject_id: str,
    role: str,
    condition_ref: str,
    expires_at,
    permissions=None,
    delegation=None,
    subject_type: str = "user",
    ip: Optional[str] = None,
) -> IamBinding:
    """Grant an engines role (0009 `create_grant`); `parent_id` comes from `_delegator`."""
    from shared.access import policy
    from shared.access import service as access
    from shared.access.models import PolicyRevision

    access.require_enabled()
    authority = policy.epoch(db, True)
    policy.authorize(db, actor, "access.grants.manage")
    if role not in policy.ROLES:
        raise _control_error("ROLE_UNKNOWN", 422)
    if subject_type != "user":
        raise _control_error("INVALID_SUBJECT", 422)
    ps = list(permissions) if permissions is not None else sorted(policy.ROLES[role])
    if not ps or not set(ps).issubset(policy.ROLES[role]):
        raise _control_error("PERMISSIONS_OUTSIDE_ROLE", 422)
    if str(subject_id) == str(actor):
        raise _control_error("SELF_GRANT", 422)
    revision = db.get(PolicyRevision, condition_ref) if condition_ref else None
    target = db.get(User, subject_id)
    if not revision or not target or not target.is_active:
        raise _control_error("GRANT_TARGET_NOT_FOUND", 404)
    try:
        expiry = to_utc_naive(expires_at)
    except IamError:
        raise _control_error("GRANT_EXPIRY_INVALID", 422) from None
    now = datetime.utcnow()
    if expiry <= now or expiry > now + timedelta(days=365):
        raise _control_error("GRANT_EXPIRY_INVALID", 422)
    if delegation is not None and hasattr(delegation, "model_dump"):
        delegation = delegation.model_dump(mode="json")
    if delegation and (
        role != "access_admin"
        or not set(delegation["permissions"]).issubset(policy.PERMISSIONS)
    ):
        raise _control_error("DELEGATION_INVALID", 422)
    parent = access._delegator(db, actor, ps, revision.constraints, expiry, delegation)

    from shared.iam.engine_mirror import mirror

    b = IamBinding(
        subject_type="user",
        subject_id=target.id,
        role=role,
        scope_type="platform",
        scope_id=None,
        permissions=ps,
        condition_ref=revision.id,
        delegation=delegation or None,
        parent_id=parent,
        granted_by=actor,
        expires_at=expiry,
        version=0,
        created_at=now,
    )
    db.add(b)
    db.flush()
    authority.version += 1
    mirror(db, b)
    _engine_audit(db, actor, GRANT_AUDIT_ACTION, b, None, view(b, now), ip)
    db.commit()
    return b


def revoke_engine(
    db: Session, actor: str, binding_id: str, version: int, *, strict: bool = False, ip: Optional[str] = None
) -> IamBinding:
    """
    Revoke an engines binding (0009 `revoke`).

    `strict=False` is the 0009 contract of `/admin/access/grants/{id}/revoke`:
    GRANT_NOT_FOUND, and a re-revocation is accepted (`version += 1`).
    `strict=True` is the unified route's: BINDING_NOT_FOUND and ALREADY_REVOKED.
    """
    from shared.access import policy
    from shared.iam.engine_mirror import mirror

    authority = policy.epoch(db, True)
    policy.authorize(db, actor, "access.grants.manage")
    b = (
        _engine_query(db)
        .filter(IamBinding.id == str(binding_id))
        .populate_existing()
        .with_for_update()
        .first()
    )
    if b is None:
        raise _control_error("BINDING_NOT_FOUND" if strict else "GRANT_NOT_FOUND", 404)
    _covered(db, actor, b)
    if strict and b.revoked_at is not None:
        raise _control_error("ALREADY_REVOKED", 409)
    if b.version != version:
        raise _control_error("VERSION_CONFLICT")
    before = view(b)
    # A re-revocation (alias path) is accepted but keeps who cut the access, and when
    if b.revoked_at is None:
        b.revoked_at = datetime.utcnow()
        b.revoked_by = str(actor)
    b.version += 1
    authority.version += 1
    db.flush()
    mirror(db, b)
    _engine_audit(db, actor, REVOKE_AUDIT_ACTION, b, before, view(b), ip)
    db.commit()
    return b


def _visible_engine_bindings(db: Session, actor: str):
    """
    Every well-formed engines binding the actor's envelope covers (the 0009
    `list_grants` filter), revoked and expired included, newest first.
    """
    from shared.engine_control.service import ControlError
    from shared.iam.engine_bindings import well_formed

    rows = []
    for b in _engine_query(db).order_by(IamBinding.created_at.desc(), IamBinding.id):
        if not well_formed(db, b):
            continue
        try:
            _covered(db, actor, b)
        except ControlError:
            continue
        rows.append(b)
    return rows


def list_engine_grants(db: Session, actor: str):
    """
    Every engines binding the actor's envelope covers (0009 `list_grants`),
    revoked and expired included, newest first. Never a platform binding.
    """
    from shared.access import policy
    from shared.iam.engine_bindings import as_grant

    policy.authorize(db, actor, "access.grants.manage")
    return [as_grant(b) for b in _visible_engine_bindings(db, actor)]


# -- the unified API (spec 0018 §4.5, CA6, CA16, CA17) --------------------------------
#
# `/admin/iam/bindings*` serve both families through the three functions below.
# Each one branches on the family **before** any check (the role for a grant,
# the target binding for a revoke) and then applies only that family's rules:
#
# - platform: `iam.bindings.read|manage` as IAM_MODE decides it (`decide.can`),
#   then the 0014 rules of `grant` / `revoke` / `list_bindings`;
# - engines: `engine_access_enabled` (else 503 ACCESS_NOT_ENABLED), then the 0009
#   rules of `grant_engine` / `revoke_engine` (bootstrap or
#   `access.grants.manage` + `_delegator`), with the strict revoke codes.
#
# Every refusal is an `IamError`, so the route answers `{code, message}` for both.

FAMILY_FIELDS = ("permissions", "condition_ref", "delegation", "parent_id")


def _engines_refused(db: Session, e) -> IamError:
    db.rollback()
    return IamError(e.code, e.status, str(e))


def _fresh_transaction(db: Session) -> None:
    """
    End the transaction the request's dependencies read in, so the engines write
    takes the 0009 epoch lock before its first read (CA5, CA17): under MySQL's
    REPEATABLE READ the snapshot is taken by the first plain read, which then
    comes after the lock, not before it. Nothing is pending here: the
    dependency already committed any bootstrap audit.
    """
    db.rollback()


def platform_authority(db: Session, principal: Principal, permission: str, decider: Decider) -> bool:
    """`iam.bindings.read|manage` as IAM_MODE decides it (bindings inert outside enforce)."""
    from shared.iam.decide import can

    return can(db, principal, permission, decider=decider)


def engines_authority(db: Session, principal: Principal) -> bool:
    """
    Bootstrap or `access.grants.manage`, only while engine access is enabled:
    with the flag off `policy.authorize` answers "bootstrap" for everyone, a
    domain-compatibility shortcut that must never open the administration.
    """
    from shared.access import policy

    if principal is None or principal.subject_type != "user" or not policy.enabled():
        return False
    return policy.allowed(db, principal.subject_id, "access.grants.manage")


def view_any(db: Session, b: IamBinding, now: Optional[datetime] = None) -> dict:
    """`view`, with `active` the 0009 decision for an engines binding (parent chain, owner)."""
    if not _engines(b):
        return view(b, now)
    from shared.iam.engine_bindings import active_grant, as_grant, well_formed

    return view(b, now, active=well_formed(db, b) and active_grant(db, as_grant(b)))


def grant_binding(
    db: Session,
    actor,
    *,
    subject_type: str,
    subject_id: str,
    role: str,
    expires_at,
    permissions=None,
    condition_ref: Optional[str] = None,
    delegation=None,
    parent_id: Optional[str] = None,
    ip: Optional[str] = None,
    decider: Optional[Decider] = None,
) -> IamBinding:
    """`POST /admin/iam/bindings`: grant a role of either family."""
    from shared.engine_control.service import ControlError

    decider = decider or Decider(db)
    principal = as_principal(actor)
    family = catalog.family(role)
    if family is None:
        raise IamError("UNKNOWN_ROLE", 422, f"Unknown role {role!r}")

    if family == catalog.ENGINES_FAMILY:
        if parent_id is not None:
            raise IamError(
                "FIELD_NOT_ALLOWED_FOR_ROLE", 422,
                "parent_id is set by the service: the delegation that authorizes the grant",
            )
        if principal is None or principal.subject_type != "user":
            raise IamError("ACCESS_DENIED", 403, "Only a user grants or revokes bindings")
        _fresh_transaction(db)
        try:
            return grant_engine(
                db,
                principal.subject_id,
                subject_type=subject_type,
                subject_id=subject_id,
                role=role,
                condition_ref=condition_ref,
                expires_at=expires_at,
                permissions=permissions,
                delegation=delegation,
                ip=ip,
            )
        except ControlError as e:
            raise _engines_refused(db, e) from None

    if not platform_authority(db, principal, "iam.bindings.manage", decider):
        raise IamError("ACCESS_DENIED", 403, "Granting a platform role needs iam.bindings.manage")
    sent = dict(permissions=permissions, condition_ref=condition_ref, delegation=delegation, parent_id=parent_id)
    extra = [name for name in FAMILY_FIELDS if sent[name] is not None]
    if extra:
        raise IamError(
            "FIELD_NOT_ALLOWED_FOR_ROLE", 422,
            f"A platform role takes no {', '.join(extra)}: only engines roles carry them",
        )
    return grant(
        db,
        principal,
        subject_type=subject_type,
        subject_id=subject_id,
        role=role,
        expires_at=expires_at,
        ip=ip,
        decider=decider,
    )


def revoke_binding(
    db: Session,
    actor,
    binding_id: str,
    *,
    version: int,
    ip: Optional[str] = None,
    decider: Optional[Decider] = None,
) -> IamBinding:
    """`POST /admin/iam/bindings/{id}/revoke`: the family is the target binding's."""
    from shared.access import service as access
    from shared.engine_control.service import ControlError

    decider = decider or Decider(db)
    principal = as_principal(actor)
    b = db.get(IamBinding, str(binding_id))
    if b is None:
        raise IamError("BINDING_NOT_FOUND", 404)

    if _engines(b):
        if principal is None or principal.subject_type != "user":
            raise IamError("ACCESS_DENIED", 403, "Only a user grants or revokes bindings")
        # CA17: the epoch lock comes before the binding is read again (locked).
        _fresh_transaction(db)
        try:
            access.require_enabled()
            return revoke_engine(db, principal.subject_id, binding_id, version, strict=True, ip=ip)
        except ControlError as e:
            raise _engines_refused(db, e) from None

    if not platform_authority(db, principal, "iam.bindings.manage", decider):
        raise IamError("ACCESS_DENIED", 403, "Revoking a platform binding needs iam.bindings.manage")
    return revoke(db, principal, binding_id, version=version, ip=ip, decider=decider)


def list_all(
    db: Session,
    actor,
    *,
    include_inactive: bool = False,
    decider: Optional[Decider] = None,
    session: bool = True,
):
    """
    `GET /admin/iam/bindings`, filtered per row: platform bindings for
    `iam.bindings.read`, engines bindings through the 0009 `_delegator` filter of
    `list_grants`. `include_inactive` applies to both; newest first. Engines
    rows need a login `session` (0009's `access_session`): an API key sees
    platform rows only.
    """
    decider = decider or Decider(db)
    principal = as_principal(actor)
    platform = platform_authority(db, principal, "iam.bindings.read", decider)
    engines = session and engines_authority(db, principal)
    if not (platform or engines):
        raise IamError("ACCESS_DENIED", 403)
    now = decider.now()
    rows = []
    if platform:
        rows += [view(b, now) for b in _platform_bindings(db, include_inactive, now)]
    if engines:
        for b in _visible_engine_bindings(db, principal.subject_id):
            row = view_any(db, b, now)
            if include_inactive or row["active"]:
                rows.append(row)
    rows.sort(key=lambda r: r["id"])
    rows.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return rows
