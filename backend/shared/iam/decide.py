"""
The single IAM decision point (spec 0014 §4.4, 0013 §4 rule 1).

    decide(principal, permission, resource) -> Decision{allow, status, via, binding_id}

1. Principal: an active user (an API key acts as its owner in this slice) or an
   active service principal. Absent → 401, inactive → 403. A null actor is never
   an admin.
2. 0009 engine permissions are not decided here: they stay in
   `shared.access.policy.authorize`. Asking for one is a programming error.
3. Platform/IAM permissions: bootstrap (`is_effective_admin`) → allow, audited
   when the permission is a mutation; an active binding whose managed role holds
   the permission → allow; otherwise 403 (the route is not a secret).
4. Data permissions: owner only, resolved exactly as `api.deps` always did
   (`shared.iam.ownership`, including the Redis parent link). Otherwise 404.
   Bootstrap reads no one else's data, as today.

Authority comes only from SQL. Bindings are read at most once per `Decider`
(one per request): there is no positive cache across requests, so a revocation
takes effect on the next request (0013 §4 rule 8).

`decide()` is the *new* decision regardless of `IAM_MODE`. Callers outside the
route dependencies (dispatcher, capability probes) use `can()`, which honours the
mode: `off` answers with the legacy rule and leaves bindings inert, `shadow`
answers with the legacy rule and logs divergences, `enforce` answers with IAM.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, FrozenSet, List, Optional

from sqlalchemy.orm import Session

from shared.admin import is_effective_admin
from shared.config import get_settings
from shared.iam import catalog, ownership
from shared.iam.models import IamBinding
from shared.models import AdminAudit, Job, User

logger = logging.getLogger(__name__)


class _Platform:
    """The resource of every platform/IAM permission (scope `platform`, id NULL)."""

    def __repr__(self):
        return "PLATFORM"


PLATFORM = _Platform()


@dataclass(frozen=True)
class JobRef:
    """A job by id, so child jobs (SPLIT/PAGE/MERGE, no row of their own) resolve too."""

    job_id: str


class UnknownPermission(ValueError):
    """Outside the closed catalog."""


class DelegatedPermission(ValueError):
    """A 0009 engine permission: decided by shared.access.policy.authorize."""


@dataclass(frozen=True)
class Principal:
    subject_type: str  # "user" | "service_principal"
    subject_id: str
    active: bool
    bootstrap: bool = False
    # "session" (JWT), "api_key" or "cli": recorded when bootstrap is audited.
    credential: str = "session"
    user: Optional[User] = field(default=None, compare=False, repr=False)


def principal_for_user(user: Optional[User], credential: str = "session") -> Optional[Principal]:
    """The principal of an authenticated user (the key's owner for an API key)."""
    if user is None or getattr(user, "id", None) is None:
        return None
    active = getattr(user, "is_active", False) is True
    return Principal(
        subject_type="user",
        subject_id=str(user.id),
        active=active,
        # Bootstrap only for an active user: deactivating an admin disables it.
        bootstrap=active and is_effective_admin(user),
        credential=credential,
        user=user,
    )


def principal_for_service(db: Session, service_principal_id: Optional[str]) -> Optional[Principal]:
    """A 0009 service principal; never bootstrap, never a data owner."""
    from shared.access.models import ServicePrincipal

    if not service_principal_id:
        return None
    row = db.get(ServicePrincipal, str(service_principal_id))
    if row is None:
        return None
    return Principal("service_principal", row.id, active=row.active is True, credential="cli")


def as_principal(principal) -> Optional[Principal]:
    if principal is None or isinstance(principal, Principal):
        return principal
    return principal_for_user(principal)


@dataclass(frozen=True)
class Decision:
    allow: bool
    status: int  # 200 when allowed; 401 / 403 / 404 otherwise
    via: str  # bootstrap | binding | owner | self_service | denied reason
    permission: str
    binding_id: Optional[str] = None
    # For data permissions on a job: the row that authorized it (see JobAccess).
    target: object = field(default=None, compare=False, repr=False)


JobAccessFn = Callable[[Session, str, Optional[str]], ownership.JobAccess]


def _permission(name: str) -> catalog.Permission:
    if catalog.is_engine_permission(name):
        raise DelegatedPermission(f"{name} is a 0009 engine permission; use shared.access.policy")
    try:
        return catalog.permission(name)
    except KeyError:
        raise UnknownPermission(name) from None


class Decider:
    """
    Decisions for one request. Memoizes the principal's active bindings for its own
    lifetime only; create a new one per request (never module-level).
    """

    def __init__(
        self,
        db: Session,
        *,
        now: Optional[datetime] = None,
        job_access: Optional[JobAccessFn] = None,
        audit_ip: Optional[str] = None,
    ):
        self.db = db
        self._now = now
        self._job_access = job_access or ownership.job_access
        self._ip = audit_ip
        self._bindings: Dict[tuple, List[IamBinding]] = {}
        self._audited: set = set()

    def now(self) -> datetime:
        """Naive UTC, like every DateTime column of this schema."""
        return self._now or datetime.utcnow()

    # -- bindings -----------------------------------------------------------------

    def bindings(self, principal: Principal) -> List[IamBinding]:
        """Active, non-expired, non-revoked platform bindings of a managed role."""
        key = (principal.subject_type, principal.subject_id)
        if key not in self._bindings:
            rows = (
                self.db.query(IamBinding)
                .filter(
                    IamBinding.subject_type == principal.subject_type,
                    IamBinding.subject_id == principal.subject_id,
                    IamBinding.revoked_at.is_(None),
                    IamBinding.scope_type == "platform",
                    IamBinding.expires_at > self.now(),
                )
                .order_by(IamBinding.created_at, IamBinding.id)
                .all()
            )
            # A role key removed from the catalog in a later deploy grants nothing.
            self._bindings[key] = [b for b in rows if b.role in catalog.ROLES]
        return self._bindings[key]

    def platform_roles(self, principal) -> List[str]:
        """Roles held through bindings (bootstrap is reported apart, never as a role)."""
        principal = as_principal(principal)
        if principal is None or not principal.active:
            return []
        return sorted({b.role for b in self.bindings(principal)})

    def platform_permissions(self, principal) -> FrozenSet[str]:
        """Every platform/IAM permission the principal holds right now."""
        principal = as_principal(principal)
        if principal is None or not principal.active:
            return frozenset()
        if principal.bootstrap:
            return catalog.ROLES[catalog.BOOTSTRAP_ROLE].permissions
        held = set()
        for b in self.bindings(principal):
            held |= catalog.ROLES[b.role].permissions
        return frozenset(held)

    # -- decision -----------------------------------------------------------------

    def decide(self, principal, permission: str, resource=PLATFORM) -> Decision:
        perm = _permission(permission)
        principal = as_principal(principal)

        if principal is None:
            return Decision(False, 401, "no_principal", permission)
        if not principal.active:
            return Decision(False, 403, "inactive", permission)

        if perm.level in (catalog.PLATFORM, catalog.IAM):
            return self._platform(principal, perm)
        return self._data(principal, perm, resource)

    def _platform(self, principal: Principal, perm: catalog.Permission) -> Decision:
        if principal.bootstrap:
            if perm.mutation:
                self._audit_bootstrap(principal, perm.name)
            return Decision(True, 200, "bootstrap", perm.name)
        for b in self.bindings(principal):
            if perm.name in catalog.ROLES[b.role].permissions:
                return Decision(True, 200, "binding", perm.name, binding_id=b.id)
        return Decision(False, 403, "no_binding", perm.name)

    def _data(self, principal: Principal, perm: catalog.Permission, resource) -> Decision:
        not_found = Decision(False, 404, "not_owner", perm.name)
        # Platform principals do not own data in this slice.
        if principal.subject_type != "user":
            return not_found

        if resource is None:
            # A lookup that found nothing (or a resource scoped away from this
            # principal). Never confused with "no resource needed": 404 always.
            return not_found
        if resource is PLATFORM:
            # Creating in one's own space needs no resource; anything else does.
            if perm.self_service:
                return Decision(True, 200, "self_service", perm.name)
            return not_found

        me = principal.subject_id
        if isinstance(resource, JobRef):
            access = self._job_access(self.db, resource.job_id, me)
            if access.allowed:
                return Decision(True, 200, "owner", perm.name, target=access.job)
            return not_found
        if isinstance(resource, Job):
            if ownership.resolve_owner_id(self.db, resource) == me:
                return Decision(True, 200, "owner", perm.name, target=resource)
            return not_found
        if ownership.owns(resource, me):
            return Decision(True, 200, "owner", perm.name, target=resource)
        return not_found

    def _audit_bootstrap(self, principal: Principal, permission: str) -> None:
        """CA8: every mutation exercised through bootstrap leaves an AdminAudit row."""
        key = (principal.subject_id, permission)
        if key in self._audited:
            return
        self._audited.add(key)
        self.db.add(
            AdminAudit(
                actor_user_id=principal.subject_id,
                # `audit_auth_method` is jwt|cli and is not widened here: an API key
                # (a user credential) is recorded as "jwt", and the exact credential
                # ("session" | "api_key" | "cli") is in `after.credential`.
                auth_method="cli" if principal.credential == "cli" else "jwt",
                ip=self._ip,
                action="iam.bootstrap.use",
                target_type="iam_permission",
                target_id=permission,
                after={
                    "permission": permission,
                    "via": "bootstrap",
                    "credential": principal.credential,
                },
            )
        )


def decide(db: Session, principal, permission: str, resource=PLATFORM, *, decider: Optional[Decider] = None) -> Decision:
    """One decision; pass the request's `decider` to share its memo."""
    return (decider or Decider(db)).decide(principal, permission, resource)


# -- mode-aware entry point --------------------------------------------------------


def legacy_allows(db: Session, principal, permission: str, resource=PLATFORM, *, decider: Optional[Decider] = None) -> bool:
    """
    The rule before 0014: platform power is `is_effective_admin` of the user,
    exactly as the worker paths check it (`workers/tasks.py` reads it off the job
    owner without looking at `is_active`); service principals hold none. Data is
    owner-only for an active user (unchanged, so it is the same code path).
    """
    perm = _permission(permission)
    principal = as_principal(principal)
    if principal is None:
        return False
    if perm.level in (catalog.PLATFORM, catalog.IAM):
        user = principal.user
        return principal.subject_type == "user" and user is not None and is_effective_admin(user)
    if not principal.active:
        return False
    return (decider or Decider(db))._data(principal, perm, resource).allow


def can(
    db: Session,
    principal,
    permission: str,
    resource=PLATFORM,
    *,
    decider: Optional[Decider] = None,
    mode: Optional[str] = None,
) -> bool:
    """
    Whether to allow, honouring IAM_MODE (0014 §4.11). Rollback to `off` only ever
    reduces access: bindings stop counting, bootstrap keeps working.
    """
    mode = mode or get_settings().iam_mode
    if mode == "off":
        allowed = legacy_allows(db, principal, permission, resource, decider=decider)
        p = as_principal(principal)
        perm = catalog.permission(permission)
        # CA8 does not depend on the mode: a bootstrap mutation is audited in off too.
        if allowed and p is not None and p.bootstrap and perm.mutation and perm.level in (catalog.PLATFORM, catalog.IAM):
            (decider or Decider(db))._audit_bootstrap(p, permission)
        return allowed
    new = decide(db, principal, permission, resource, decider=decider).allow
    if mode == "enforce":
        return new
    if catalog.permission(permission).level not in (catalog.PLATFORM, catalog.IAM):
        # Data permissions: legacy and IAM are the same code path; resolve once.
        return new
    legacy = legacy_allows(db, principal, permission, resource, decider=decider)
    if legacy != new:
        report_divergence(permission, principal, legacy=legacy, iam=new)
    return legacy


def report_divergence(permission: str, principal, *, legacy: bool, iam: bool, route: Optional[str] = None) -> None:
    """
    Shadow mode: the legacy rule and IAM disagree (0014 §4.11 step 2).

    One structured log line per divergence. The fields are the labels of the
    planned `iam_shadow_divergence_total{route,permission}` metric (§6); the
    project has no metrics facility yet, so the log is the signal.
    """
    p = as_principal(principal)
    fields = {
        "route": route,
        "permission": permission,
        "subject": p.subject_id if p else None,
        "legacy": legacy,
        "iam": iam,
    }
    # The fields go in the message itself: the API's log format (api/main.py)
    # prints only %(message)s, never `extra`. `extra` stays for structured handlers.
    logger.warning(
        "iam_shadow_divergence " + " ".join(f"{k}={v}" for k, v in fields.items()),
        extra=fields,
    )
