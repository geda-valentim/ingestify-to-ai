"""
IAM API (spec 0014 §4.9).

    GET  /iam/permissions                   any session: the closed catalog and managed roles
    POST /iam/check                         any session: [{permission}] -> [{permission, allowed}],
                                            platform/IAM permissions only in this slice
    GET  /admin/iam/bindings                iam.bindings.read
    POST /admin/iam/bindings                iam.bindings.manage + login session (JWT)
    POST /admin/iam/bindings/{id}/revoke    iam.bindings.manage + login session (JWT)

Errors carry `{"code", "message"}` in `detail`: 401 no session; 403 platform
permission missing (or an API key on a write); 404 unknown binding; 409 version
conflict, already revoked or an active binding for the same role; 422 unknown
role, self-grant, a role above the grantor or an invalid `expires_at`.

A platform binding never opens the 0009 engine routes: `access_session` still
reads only the 0009 grants (§4.9, tested).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.iam_deps import (
    authenticated,
    platform_view,
    request_decider,
    request_principal,
    require,
)
from shared.iam import bindings, catalog
from shared.iam.decide import Decider
from shared.models import User

router = APIRouter(tags=["IAM"])

MAX_CHECKS = 100

# Writes need a login session, as `require_admin_session` always did (§4.7, §4.9).
MANAGE = require(
    "iam.bindings.manage",
    session=True,
    session_detail="Changing platform access requires a login session (JWT); API keys are not accepted",
)


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


class BindingRevoke(BaseModel):
    version: int


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _iam_error(e: bindings.IamError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "message": e.detail})


@router.get("/iam/permissions", summary="The permission catalog and the managed roles")
async def list_permissions(user: User = Depends(authenticated())):
    return catalog.describe()


@router.post("/iam/check", response_model=List[PermissionCheckResult], summary="Which platform permissions the caller holds")
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


@router.get("/admin/iam/bindings", summary="Platform bindings")
def list_bindings(
    request: Request,
    include_inactive: bool = False,
    user: User = Depends(require("iam.bindings.read")),
    decider: Decider = Depends(request_decider),
):
    try:
        rows = bindings.list_bindings(
            decider.db, request_principal(request, user), include_inactive=include_inactive, decider=decider
        )
    except bindings.IamError as e:
        raise _iam_error(e)
    return {"bindings": rows}


@router.post("/admin/iam/bindings", status_code=201, summary="Grant a platform role")
def grant_binding(
    body: BindingCreate,
    request: Request,
    user: User = Depends(MANAGE),
    decider: Decider = Depends(request_decider),
):
    try:
        b = bindings.grant(
            decider.db,
            request_principal(request, user),
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            role=body.role,
            expires_at=body.expires_at,
            ip=_client_ip(request),
            decider=decider,
        )
    except bindings.IamError as e:
        decider.db.rollback()
        raise _iam_error(e)
    return bindings.view(b, decider.now())


@router.post("/admin/iam/bindings/{binding_id}/revoke", summary="Revoke a platform binding")
def revoke_binding(
    binding_id: str,
    body: BindingRevoke,
    request: Request,
    user: User = Depends(MANAGE),
    decider: Decider = Depends(request_decider),
):
    try:
        b = bindings.revoke(
            decider.db,
            request_principal(request, user),
            binding_id,
            version=body.version,
            ip=_client_ip(request),
            decider=decider,
        )
    except bindings.IamError as e:
        decider.db.rollback()
        raise _iam_error(e)
    return bindings.view(b, decider.now())
