"""
IAM API (spec 0014 §4.9; spec 0018 §4.5).

    GET  /iam/permissions                   any session: the closed catalog and managed roles
    POST /iam/check                         any session: [{permission}] -> [{permission, allowed}],
                                            platform/IAM permissions only
    GET  /admin/iam/bindings                either family's administration, rows filtered per family
    POST /admin/iam/bindings                either family's administration + login session (JWT)
    POST /admin/iam/bindings/{id}/revoke    either family's administration + login session (JWT)

Since spec 0018 the bindings routes serve both role families, each with its own
authority and rules, which never cross (`shared.iam.bindings.grant_binding`,
`revoke_binding`, `list_all`):

- `platform` (0014): `iam.bindings.read|manage` as IAM_MODE decides it; self-grant,
  role above the grantor, one active binding per (subject, role);
- `engines` (0009): bootstrap or `access.grants.manage` + the delegation envelope,
  a mandatory `condition_ref` (policy revision), materialized `permissions`,
  `delegation` for `access_admin` only, several bindings of one role per user;
  503 ACCESS_NOT_ENABLED while `engine_access_enabled` is false.

Handler errors carry `{"code", "message"}` in `detail` (codes per family in 0018
§4.5). The 401 (no session) and 403 (no family's administration, or an API key
on a write) come from the dependency and keep the legacy plain-string `detail`
of `require_admin` (0014 CA12). `/admin/access/grants*` are deprecated aliases
for the engines family with the 0009 contract.

A platform binding never opens the 0009 engine routes: `access_session` reads
only engines-family bindings, through `shared.access.policy.navigation` (§4.9,
tested; spec 0018 CA13).
"""

from typing import List, Optional

from api.error_guidance import GuidedRoute
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.iam_deps import (
    BindingAdmin,
    authenticated,
    binding_admin,
    is_login_session,
    platform_view,
    request_decider,
    request_principal,
)
from shared.access.contracts import Delegation
from shared.config import get_settings
from shared.iam import bindings, catalog
from shared.iam.decide import Decider
from shared.models import User

router = APIRouter(tags=["IAM"], route_class=GuidedRoute)

MAX_CHECKS = 100



class PermissionCheck(BaseModel):
    permission: str


class PermissionCheckResult(BaseModel):
    permission: str
    allowed: bool


class BindingCreate(BaseModel):
    subject_type: str = "user"
    subject_id: str
    role: str
    # ISO-8601; an aware value is converted to UTC, a naive one is taken as UTC.
    # Required, in the future and at most 365 days away (CA7).
    expires_at: Optional[str] = Field(None, examples=["2027-01-31T00:00:00Z"])
    # Engines roles only (spec 0018 CA6); any of them on a platform role is a
    # 422 FIELD_NOT_ALLOWED_FOR_ROLE.
    # The 0009 permission subset; omitted = every permission of the role, stored
    # materialized (a later action added to the role never widens the binding).
    permissions: Optional[List[str]] = Field(None, max_length=100)
    # The condition: an access policy revision id. Required for an engines role.
    condition_ref: Optional[str] = None
    # The delegation envelope, `access_admin` only.
    delegation: Optional[Delegation] = None
    # Set by the service (the delegation that authorizes the grant), never by
    # the caller: refused on both families.
    parent_id: Optional[str] = None


class BindingRevoke(BaseModel):
    version: int


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _iam_error(e: bindings.IamError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "message": e.detail})


@router.get("/iam/permissions", summary="Catálogo de permissões e papéis gerenciados")
async def list_permissions(user: User = Depends(authenticated())):
    # `mode` lets the UI say that bindings are inert until IAM_MODE=enforce (§4.11).
    return {**catalog.describe(), "mode": get_settings().iam_mode}


@router.post("/iam/check", response_model=List[PermissionCheckResult], summary="Verificar permissões de plataforma do chamador")
def check_permissions(
    body: List[PermissionCheck],
    request: Request,
    user: User = Depends(authenticated()),
    decider: Decider = Depends(request_decider),
):
    """
    Answers for the caller only, as IAM_MODE decides it, and never audits (asking
    is not exercising). Only platform/IAM permissions in this slice: a data or 0009
    engine permission, or a name outside the catalog, is a 422.
    """
    if len(body) > MAX_CHECKS:
        raise HTTPException(status_code=422, detail={"code": "TOO_MANY_CHECKS", "message": f"At most {MAX_CHECKS} checks"})
    unsupported = sorted({c.permission for c in body if c.permission not in catalog.PLATFORM_PERMISSIONS})
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_PERMISSION",
                "message": f"Only platform permissions can be checked: {', '.join(unsupported)}",
            },
        )
    held = platform_view(decider, request_principal(request, user)).permissions
    return [PermissionCheckResult(permission=c.permission, allowed=c.permission in held) for c in body]


@router.get("/admin/iam/bindings", summary="Listar vínculos de plataforma e de engines")
def list_bindings(
    request: Request,
    include_inactive: bool = False,
    admin: BindingAdmin = Depends(binding_admin(write=False)),
    decider: Decider = Depends(request_decider),
):
    """
    Filtered per row: platform bindings for `iam.bindings.read` (as IAM_MODE
    decides it); engines bindings the caller's 0009 delegation covers (bootstrap
    sees them all), with `engine_access_enabled`. Newest first.
    """
    try:
        rows = bindings.list_all(
            decider.db,
            admin.principal,
            include_inactive=include_inactive,
            decider=decider,
            session=is_login_session(request),
        )
    except bindings.IamError as e:
        raise _iam_error(e)
    return {"bindings": rows}


@router.post("/admin/iam/bindings", status_code=201, summary="Conceder papel de plataforma ou de engines")
def grant_binding(
    body: BindingCreate,
    request: Request,
    admin: BindingAdmin = Depends(binding_admin(write=True)),
    decider: Decider = Depends(request_decider),
):
    try:
        b = bindings.grant_binding(
            decider.db,
            admin.principal,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            role=body.role,
            expires_at=body.expires_at,
            permissions=body.permissions,
            condition_ref=body.condition_ref,
            delegation=body.delegation,
            parent_id=body.parent_id,
            ip=_client_ip(request),
            decider=decider,
        )
    except bindings.IamError as e:
        decider.db.rollback()
        raise _iam_error(e)
    return bindings.view_any(decider.db, b, decider.now())


@router.post("/admin/iam/bindings/{binding_id}/revoke", summary="Revogar vínculo de plataforma ou de engines")
def revoke_binding(
    binding_id: str,
    body: BindingRevoke,
    request: Request,
    admin: BindingAdmin = Depends(binding_admin(write=True)),
    decider: Decider = Depends(request_decider),
):
    try:
        b = bindings.revoke_binding(
            decider.db,
            admin.principal,
            binding_id,
            version=body.version,
            ip=_client_ip(request),
            decider=decider,
        )
    except bindings.IamError as e:
        decider.db.rollback()
        raise _iam_error(e)
    return bindings.view_any(decider.db, b, decider.now())
