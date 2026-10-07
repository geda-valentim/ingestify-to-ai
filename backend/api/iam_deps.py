"""
FastAPI dependencies that declare and decide authorization (spec 0014 §4.1, §4.5).

Every HTTP/WS route declares **exactly one** of these (CA1, enforced by
`tests/test_iam_route_coverage.py`):

    require("platform.stats.read")            platform/IAM permission, or a
    require("p", session=True)                 self-service data permission
                                               ("create in my own space")
    authorized(Job, "jobs.read")               loads the resource named by the path
                                               and decides on it; returns what the
                                               legacy `get_owned_*` returned
    visible(Job, "jobs.read")                  a `Scope` whose `.predicate` the
                                               listing applies to its query
    engine_access()                            marker only: a 0009 route, still
                                               decided by `access_session` /
                                               `require_admin_session` and
                                               `shared.access.policy`
    authenticated()                            any active user, about themselves
                                               only (`/auth/me`, `/iam/*`): the
                                               "sessão" of 0014 §4.9

## IAM_MODE (0014 §4.11)

- `off`     — exactly the legacy rule (`is_effective_admin`, `api.deps` owner
              checks); bindings are inert.
- `shadow`  — `require` and `authorized` evaluate both; the **legacy** decision
              answers and a divergence logs `iam_shadow_divergence`. `visible`
              has no shadow: its predicate *is* the legacy filter (§4.5, §5).
- `enforce` — `shared.iam.decide` answers.

The mode is read per request, so tests (and an operator) can switch it without
re-importing the routes.

Decisions share one `Decider` per request (`request.state`), so bindings are
read at most once per request and never cached across requests (0013 §4 rule 8).
"""

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api import deps
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import get_db
from shared.iam import catalog
from shared.iam.decide import (
    PLATFORM,
    Decider,
    Decision,
    JobRef,
    Principal,
    legacy_allows,
    principal_for_user,
    report_divergence,
)
from shared.models import AdminAudit, APIKey, Folder, Job, Page, Project, User

logger = logging.getLogger(__name__)

# Same text as `admin_routes.require_admin`: converting a route changes no contract (CA12).
PLATFORM_DENIED_DETAIL = "Acesso negado: privilégios de administrador necessários"
SESSION_REQUIRED_DETAIL = "This change requires a login session (JWT); API keys are not accepted"


# ============================================
# Declarations (read by the coverage test)
# ============================================

@dataclass(frozen=True)
class Declaration:
    kind: str  # require | authorized | visible | engine_access | authenticated
    permission: Optional[str] = None
    model: Optional[type] = None
    session: bool = False


def declaration_of(call: Any) -> Optional[Declaration]:
    """The authorization a dependency callable declares, if any."""
    return getattr(call, "__iam__", None)


def _declare(fn: Callable, decl: Declaration, name: str) -> Callable:
    fn.__iam__ = decl
    fn.__name__ = fn.__qualname__ = name
    return fn


# ============================================
# Per-request context
# ============================================

def request_decider(request: Request, db: Session = Depends(get_db)) -> Decider:
    """One `Decider` per request, shared by every IAM dependency of that request."""
    decider = getattr(request.state, "iam_decider", None)
    if decider is None or decider.db is not db:
        decider = Decider(
            db,
            # Through `api.deps`, so the Redis fallbacks stay patchable in one place.
            job_access=lambda s, job_id, user_id: deps.job_access(s, job_id, user_id),
            audit_ip=request.client.host if request.client else None,
        )
        request.state.iam_decider = decider
    return decider


def request_principal(request: Request, user: User) -> Principal:
    """The authenticated user; an API key acts as its owner in this slice (0014 §2)."""
    credential = "api_key" if getattr(request.state, "api_key", None) is not None else "session"
    return principal_for_user(user, credential=credential)


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    return f"{request.method} {path}"


def is_login_session(request: Request) -> bool:
    """The rule of `require_admin_session`: a Bearer JWT and no X-API-Key."""
    return not request.headers.get("x-api-key") and request.headers.get(
        "authorization", ""
    ).lower().startswith("bearer ")


def _mode() -> str:
    return get_settings().iam_mode


def _shadow(request: Request, principal: Principal, permission: str, legacy: bool, evaluate: Callable[[], Decision]) -> None:
    """
    Shadow: evaluate the new decision *after* the legacy one and compare. The legacy
    answer never depends on the new path: if it raises (e.g. `iam_bindings` missing
    on a host where the migration has not run), it is logged and ignored.
    """
    route = _route_label(request)
    try:
        new = evaluate()
    except Exception:
        logger.exception(f"iam_shadow_error route={route} permission={permission}")
        return
    if legacy != new.allow:
        report_divergence(permission, principal, legacy=legacy, iam=new.allow, route=route)


def _flush_audit(db: Session) -> None:
    """
    CA8: a bootstrap mutation leaves an AdminAudit row. Written before the handler
    runs, so the use is recorded even if the handler then fails.
    """
    if any(isinstance(obj, AdminAudit) for obj in db.new):
        db.commit()


# ============================================
# require(permission)
# ============================================

def _check_require_permission(permission: str) -> catalog.Permission:
    if catalog.is_engine_permission(permission):
        raise ValueError(f"{permission} is a 0009 engine permission: declare engine_access()")
    perm = catalog.permission(permission)  # KeyError outside the closed catalog
    if perm.level == catalog.OWNER and not perm.self_service:
        raise ValueError(f"{permission} needs a resource: use authorized() or visible()")
    return perm


def require(permission: str, *, session: bool = False, session_detail: str = SESSION_REQUIRED_DETAIL):
    """
    A platform/IAM permission (decided on PLATFORM), or a self-service data
    permission such as `documents.convert`. `session=True` additionally demands a
    login session, as `require_admin_session` does; the permission is checked
    first, so a non-admin still gets the permission 403.

    Returns the current user, like `require_admin`.
    """
    perm = _check_require_permission(permission)

    # Plain `def`, like `require_admin`: the bindings query and the audit commit
    # are blocking DB I/O, so FastAPI runs it in the threadpool.
    def dependency(
        request: Request,
        user: User = Depends(get_current_active_user),
        decider: Decider = Depends(request_decider),
    ) -> User:
        principal = request_principal(request, user)
        mode = _mode()
        db = decider.db

        if mode == "enforce":
            decision = decider.decide(principal, permission, PLATFORM)
            allowed, status = decision.allow, decision.status
        else:
            allowed = legacy_allows(db, principal, permission, PLATFORM, decider=decider)
            status = 200 if allowed else 403
            if mode == "shadow":
                _shadow(request, principal, permission, allowed, lambda: decider.decide(principal, permission, PLATFORM))
            if allowed and principal.bootstrap and perm.mutation and perm.level != catalog.OWNER:
                # CA8 does not depend on the mode (same as `decide.can`), nor on the
                # shadow evaluation succeeding. Deduplicated per request.
                decider._audit_bootstrap(principal, permission)

        if not allowed:
            if perm.level == catalog.OWNER:
                # Only an absent/inactive principal is refused a self-service permission.
                raise HTTPException(status_code=status if status in (401, 403) else 403, detail="Inactive user")
            logger.warning(f"[IAM] {permission} denied for user {user.id}")
            raise HTTPException(status_code=403, detail=PLATFORM_DENIED_DETAIL)

        if session and not is_login_session(request):
            raise HTTPException(status_code=403, detail=session_detail)

        _flush_audit(db)
        return user

    suffix = "_session" if session else ""
    return _declare(dependency, Declaration("require", permission, session=session), f"require[{permission}]{suffix}")


# ============================================
# authorized(Model, permission)
# ============================================

@dataclass(frozen=True)
class _Loader:
    """How one model is found by its path parameter, and how legacy decided on it."""

    param: str
    family: Tuple[str, ...]
    # The legacy dependency body: the value the route got, or an HTTPException 404.
    legacy: Callable[[Session, str, User], Any]
    # What `decide()` receives as the resource.
    resource: Callable[[Session, str], Any]
    # The 404 the legacy path raises (same detail, same error_code).
    not_found: Callable[[], HTTPException]
    # The path parameter's type, as the legacy route declared it: a malformed id
    # keeps its 422 instead of becoming a 404 (CA12).
    annotation: Any = str


_LOADERS: Dict[type, _Loader] = {
    Job: _Loader(
        param="job_id",
        family=("jobs",),
        legacy=lambda db, job_id, user: deps.resolve_owned_job(db, job_id, user),
        # A JobRef, so child jobs (SPLIT/PAGE/MERGE, no row of their own) resolve.
        resource=lambda db, job_id: JobRef(job_id),
        not_found=lambda: HTTPException(status_code=404, detail=deps.JOB_NOT_FOUND_DETAIL),
    ),
    Project: _Loader(
        param="project_id",
        family=("projects",),
        legacy=lambda db, project_id, user: deps.owned_project_or_404(db, project_id, user),
        resource=lambda db, project_id: db.get(Project, str(project_id)) if project_id else None,
        not_found=lambda: deps.LocationError(404, "PROJECT_NOT_FOUND", deps.PROJECT_NOT_FOUND_DETAIL),
    ),
    Folder: _Loader(
        param="folder_id",
        family=("folders",),
        legacy=lambda db, folder_id, user: deps.owned_folder_or_404(db, folder_id, user),
        resource=lambda db, folder_id: db.get(Folder, str(folder_id)) if folder_id else None,
        not_found=lambda: deps.LocationError(404, "FOLDER_NOT_FOUND", deps.FOLDER_NOT_FOUND_DETAIL),
    ),
    APIKey: _Loader(
        param="key_id",
        family=("api_keys",),
        legacy=lambda db, key_id, user: deps.owned_api_key_or_404(db, key_id, user),
        resource=lambda db, key_id: db.get(APIKey, str(key_id)) if key_id else None,
        not_found=lambda: HTTPException(status_code=404, detail=deps.API_KEY_NOT_FOUND_DETAIL),
        annotation=UUID,
    ),
}


def _check_data_permission(model: type, permission: str, families: Tuple[str, ...]) -> catalog.Permission:
    perm = catalog.permission(permission)  # KeyError outside the closed catalog
    if perm.level != catalog.OWNER:
        raise ValueError(f"{permission} is not a data permission: use require()")
    if permission.split(".", 1)[0] not in families:
        raise ValueError(f"{permission} does not apply to {model.__name__}")
    return perm


def authorized(model: type, permission: str, *, param: Optional[str] = None):
    """
    Loads `model` by its path parameter and decides `permission` on it (§4.4 step 4).

    Drop-in for the legacy dependency: returns what `get_owned_job` /
    `get_owned_project` / `get_owned_folder` (and the inline API key lookup)
    returned, and denies with the same 404 (identical for missing and someone
    else's).
    """
    if model not in _LOADERS:
        raise ValueError(f"authorized() does not know how to load {model.__name__}")
    loader = _LOADERS[model]
    _check_data_permission(model, permission, loader.family)
    name = param or loader.param

    # Plain `def` (threadpool): the ownership lookup is blocking DB/Redis I/O.
    def dependency(
        request: Request,
        resource_id: str,
        user: User = Depends(get_current_active_user),
        decider: Decider = Depends(request_decider),
    ):
        db = decider.db
        mode = _mode()

        if mode == "enforce":
            principal = request_principal(request, user)
            decision = decider.decide(principal, permission, loader.resource(db, resource_id))
            if decision.allow:
                return decision.target
            if decision.status == 404:
                raise loader.not_found()
            raise HTTPException(status_code=decision.status, detail="Acesso negado")

        if mode == "off":
            return loader.legacy(db, resource_id, user)

        # shadow (§4.11 step 2): legacy runs first and answers; the new decision is
        # evaluated after it and can neither change nor break that answer. This
        # resolves ownership twice per request, a cost of the rollout window only.
        principal = request_principal(request, user)

        def evaluate() -> Decision:
            return decider.decide(principal, permission, loader.resource(db, resource_id))

        try:
            value = loader.legacy(db, resource_id, user)
        except HTTPException:
            _shadow(request, principal, permission, False, evaluate)
            raise
        _shadow(request, principal, permission, True, evaluate)
        return value

    # The path parameter keeps its name in the route (`/jobs/{job_id}`), so the
    # signature is rewritten: FastAPI reads `inspect.signature`.
    sig = inspect.signature(dependency)
    params = [
        p.replace(name=name, annotation=loader.annotation) if p.name == "resource_id" else p
        for p in sig.parameters.values()
    ]
    inner = dependency

    def bound(**kwargs):
        kwargs["resource_id"] = kwargs.pop(name)
        return inner(**kwargs)

    bound.__signature__ = sig.replace(parameters=params)
    return _declare(bound, Declaration("authorized", permission, model), f"authorized[{model.__name__}:{permission}]")


# ============================================
# visible(Model, permission)
# ============================================

@dataclass(frozen=True)
class Scope:
    """
    What a listing may show. In this slice `predicate` is literally
    `Model.user_id == me`, so SQL, indexes and plans do not change (CA4); 0016 adds
    `org_id` and 0017 the sharing branches here, without reopening the queries.
    """

    predicate: Any
    user: User
    permission: str

    def of(self, model: type) -> Any:
        """
        The same principal's view of a related model, for a listing that also
        counts or joins it (`GET /projects` counts jobs, folders and keys, `GET
        /api-keys` names the bound projects). The route still declares one
        `visible(...)`; the related predicate is today the same owner filter,
        `Model.user_id == me`, and is where 0016/0017 widen it per model.
        """
        if model not in _VISIBLE_FAMILIES:
            raise ValueError(f"visible() has no scope for {model.__name__}")
        return model.user_id == self.user.id


_VISIBLE_FAMILIES: Dict[type, Tuple[str, ...]] = {
    Job: ("jobs", "search"),
    Project: ("projects",),
    Folder: ("folders",),
    APIKey: ("api_keys",),
}


def visible(model: type, permission: str):
    """A `Scope` for listing `model` under `permission`. No shadow: see module doc."""
    if model not in _VISIBLE_FAMILIES:
        raise ValueError(f"visible() has no scope for {model.__name__}")
    _check_data_permission(model, permission, _VISIBLE_FAMILIES[model])
    column = model.user_id

    async def dependency(user: User = Depends(get_current_active_user)) -> Scope:
        return Scope(predicate=column == user.id, user=user, permission=permission)

    return _declare(dependency, Declaration("visible", permission, model), f"visible[{model.__name__}:{permission}]")


def owned_page(job_dependency: Callable):
    """
    The page `page_number` of the job authorized by `job_dependency` (an
    `authorized(Job, ...)`), or None when MySQL has no such page: page routes keep
    their Redis fallback, as `api.deps.get_owned_page_or_none` did.

    It declares nothing of its own: the route's one declaration is the job
    dependency, so a route that takes both the job and the page passes the *same*
    `authorized(...)` object to each and FastAPI resolves it once.
    """
    if not (declaration_of(job_dependency) and declaration_of(job_dependency).model is Job):
        raise ValueError("owned_page() needs an authorized(Job, ...) dependency")

    def dependency(
        job_id: str,
        page_number: int,
        owned_job: Optional[Job] = Depends(job_dependency),
        db: Session = Depends(get_db),
    ) -> Optional[Page]:
        return (
            db.query(Page)
            .filter(Page.job_id == job_id, Page.page_number == page_number)
            .first()
        )

    dependency.__name__ = dependency.__qualname__ = "owned_page"
    return dependency


# ============================================
# engine_access() — 0009 marker
# ============================================

def engine_access(note: str = "0009"):
    """
    Marks a 0009 engine/profile/access route in the inventory (0014 §2, §4.7).

    It decides nothing: those routes stay under `access_session` /
    `require_admin_session` and `shared.access.policy.authorize`, unchanged. The
    coverage test checks that a marked route still has one of those guards.
    """

    def dependency() -> None:
        return None

    return _declare(dependency, Declaration("engine_access", note), f"engine_access[{note}]")


# ============================================
# authenticated() — "sessão" (0014 §4.9)
# ============================================

def authenticated():
    """
    Any active user, for routes that only describe the caller to themselves
    (`/auth/me`, `/iam/permissions`, `/iam/check`). It reads no one else's data
    and grants nothing, so there is no permission to decide. Returns the user.
    """

    async def dependency(user: User = Depends(get_current_active_user)) -> User:
        return user

    return _declare(dependency, Declaration("authenticated"), "authenticated")


@dataclass(frozen=True)
class PlatformView:
    """What the caller holds at platform level right now, as IAM_MODE answers it."""

    bootstrap: bool
    roles: Tuple[str, ...]
    permissions: frozenset


def platform_view(decider: Decider, principal: Principal, mode: Optional[str] = None) -> PlatformView:
    """
    The platform permissions and roles that *count* under the current mode.

    - `enforce`: bootstrap or the active bindings (`Decider.platform_permissions`).
    - `off` / `shadow`: the legacy rule answers, so only bootstrap holds platform
      power and bindings are inert: reported roles are empty, never misleading.

    Never audits: describing a permission is not exercising it (CA8 audits uses).
    """
    mode = mode or _mode()
    if principal is None or not principal.active:
        return PlatformView(False, (), frozenset())
    if mode == "enforce":
        return PlatformView(
            principal.bootstrap,
            tuple(decider.platform_roles(principal)),
            decider.platform_permissions(principal),
        )
    held = catalog.ROLES[catalog.BOOTSTRAP_ROLE].permissions if principal.bootstrap else frozenset()
    return PlatformView(principal.bootstrap, (), held)
