"""
User management view for platform administrators: every user, what each one uses
and which API keys each one holds. Read-only.

Both routes declare `platform.users.read`, held by `platform_admin` (and so by the
bootstrap admin and the root user) and by no other managed role. The queries live
in `shared.admin_users`.
"""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.admin_errors import refusal
from api.iam_deps import is_login_session, request_principal, require
from shared import admin_users
from shared.database import get_db
from shared.iam import bindings as iam_bindings

router = APIRouter(prefix="/admin", tags=["Admin - Users"])


class AdminUserSummary(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    is_admin: bool
    is_root: bool
    created_at: Optional[str] = None
    api_keys_active: int
    projects_total: int
    jobs_total: int
    jobs_by_status: Dict[str, int]
    bytes_uploaded: int
    pages_total: int
    last_job_at: Optional[str] = None
    last_api_key_used_at: Optional[str] = None


class AdminUserList(BaseModel):
    total: int
    orphan_jobs: int
    items: List[AdminUserSummary]


class AdminUserApiKey(BaseModel):
    id: str
    name: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None
    expired: bool
    project_id: Optional[str] = None


class AdminUserProject(BaseModel):
    id: str
    name: str
    archived: bool
    created_at: Optional[str] = None
    folder_count: int
    jobs_total: int


class AdminUserRecentUsage(BaseModel):
    jobs: int
    bytes: int
    pages: int


class AdminUserUsage(BaseModel):
    by_source_type: Dict[str, int]
    last_30_days: AdminUserRecentUsage


class AdminUserDetail(AdminUserSummary):
    api_keys: List[AdminUserApiKey]
    projects: List[AdminUserProject]
    usage: AdminUserUsage
    iam_bindings: List[Dict[str, Any]]


@router.get("/users", summary="Listar usuários com uso", response_model=AdminUserList)
def list_users(
    q: Optional[str] = Query(None, max_length=255, description="Filtra por e-mail ou username (contém, sem caixa)"),
    sort: Literal["created_at", "last_job_at", "jobs_total", "bytes_uploaded"] = Query("last_job_at"),
    order: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_user=Depends(require("platform.users.read")),
    db: Session = Depends(get_db),
):
    """
    Todos os usuários (ativos e inativos) com um resumo de uso: jobs por status, bytes enviados, páginas,
    último job, chaves utilizáveis, projetos e último uso de chave. O uso conta só jobs de nível superior.
    Usuários sem o campo de ordenação vão para o fim. `orphan_jobs` conta jobs cujo dono foi apagado.
    """
    return admin_users.list_users(db, q=q, sort=sort, descending=order == "desc", limit=limit, offset=offset)


@router.get("/users/{user_id}", summary="Detalhar usuário", response_model=AdminUserDetail)
def get_user(
    user_id: str,
    request: Request,
    admin_user=Depends(require("platform.users.read")),
    db: Session = Depends(get_db),
):
    """
    O resumo do usuário mais as API keys (metadados, nunca o segredo nem o hash), os projetos com pastas e
    jobs, o uso por tipo de fonte e nos últimos 30 dias, e os bindings de IAM ativos dele. Bindings de engines
    aparecem só para quem os veria em `GET /admin/iam/bindings` (autoridade de engines e sessão de login).
    """
    # Same rule as GET /admin/iam/bindings: engines rows need engines authority and a login session.
    principal = request_principal(request, admin_user)
    viewer = principal.subject_id if (
        is_login_session(request) and iam_bindings.engines_authority(db, principal)
    ) else None
    detail = admin_users.get_user(db, user_id, engines_viewer=viewer)
    if detail is None:
        raise refusal(404, "USER_NOT_FOUND", params={"user_id": user_id})
    return detail
