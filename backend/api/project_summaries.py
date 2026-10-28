"""
Project summaries, limits and usage (specs 0004 and 0023): `GET /projects` and
`GET /projects/{project_id}`.

The usage is counted by the same functions as the PROJECT_LIMIT / FOLDER_LIMIT
refusals (`shared.projects`), so a client reads exactly how far it is from them.
`usage.projects` is always the calling principal's (the key's owner for an API
key), never the project owner's: on a project shared through IAM, the owner's
count would tell how many projects someone else has.

The router is included by `api.projects_api` after `/projects/resolve`, which the
`/projects/{project_id}` path would otherwise capture.
"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.iam_deps import Scope, authorized, visible
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import get_db
from shared.models import APIKey, Folder, Job, JobStatus as DBJobStatus, Project, User
from shared.projects import count_projects, folder_counts, name_key
from shared.schemas import ProjectRef


class ProjectFolderSummary(BaseModel):
    id: str
    name: str
    job_count: int


class ProjectSummary(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    archived: bool
    job_count: int
    root_job_count: int = Field(..., description="Jobs of the project that are in no folder")
    failed_count: int
    active_count: int = Field(..., description="Jobs queued or processing")
    last_job_at: Optional[datetime] = None
    folder_count: int = Field(..., description="Pastas do projeto, todas, contadas como o FOLDER_LIMIT conta")
    api_keys: List[ProjectRef] = Field(..., description="API keys bound to this project")
    folders: Optional[List[ProjectFolderSummary]] = Field(None, description="Only with ?include=folders")


class ProjectLimits(BaseModel):
    max_projects: int = Field(..., description="0 = sem limite")
    max_folders_per_project: int = Field(..., description="0 = sem limite")


class ProjectUsage(BaseModel):
    projects: int = Field(..., description="Projetos do usuário que chama (dono da API key), arquivados inclusive, "
                                           "contados como o PROJECT_LIMIT conta")
    folders: Optional[int] = Field(None, description="Pastas deste projeto (só no detalhe)")


class ProjectListResponse(BaseModel):
    projects: List[ProjectSummary]
    limits: ProjectLimits
    usage: ProjectUsage


class ProjectDetailResponse(BaseModel):
    project: ProjectSummary
    limits: ProjectLimits
    usage: ProjectUsage


router = APIRouter(tags=["Projects"])

_ACTIVE = (DBJobStatus.PENDING, DBJobStatus.PROCESSING)


def _wants_folders(include: Optional[str]) -> bool:
    return "folders" in {part.strip() for part in (include or "").split(",")}


def _limits() -> ProjectLimits:
    settings = get_settings()
    return ProjectLimits(max_projects=settings.max_projects_per_user,
                         max_folders_per_project=settings.max_folders_per_project)


def summarize(db: Session, scope: Scope, projects: List[Project], with_folders: bool) -> List[ProjectSummary]:
    """
    Summaries of `projects`, the most recent first (`last_job_at` desc, then name).
    A fixed number of queries whatever the number of projects: one `GROUP BY
    project_id, folder_id, status` over the jobs, one over the folders, the keys,
    and the folders themselves with `?include=folders`.
    """
    ids = [p.id for p in projects]
    stats = {p.id: {"job_count": 0, "root_job_count": 0, "failed_count": 0, "active_count": 0,
                    "last_job_at": None} for p in projects}
    jobs_by_folder: Dict[str, int] = {}

    rows = (
        db.query(Job.project_id, Job.folder_id, Job.status, func.count(Job.id), func.max(Job.created_at))
        .filter(scope.of(Job), Job.job_type == "MAIN", Job.project_id.in_(ids))
        .group_by(Job.project_id, Job.folder_id, Job.status)
        .all()
    ) if ids else []
    for project_id, folder_id, status, count, last in rows:
        st = stats.get(project_id)
        if st is None:
            continue  # a job pointing at a deleted project
        st["job_count"] += count
        if folder_id is None:
            st["root_job_count"] += count
        else:
            jobs_by_folder[folder_id] = jobs_by_folder.get(folder_id, 0) + count
        if status == DBJobStatus.FAILED:
            st["failed_count"] += count
        elif status in _ACTIVE:
            st["active_count"] += count
        if last is not None and (st["last_job_at"] is None or last > st["last_job_at"]):
            st["last_job_at"] = last

    folders_total = folder_counts(db, ids)

    keys_by_project: Dict[str, List[ProjectRef]] = {}
    for key_id, key_name, project_id in (
        db.query(APIKey.id, APIKey.name, APIKey.project_id)
        .filter(scope.of(APIKey), APIKey.project_id.in_(ids))
        .order_by(APIKey.name)
    ) if ids else []:
        keys_by_project.setdefault(project_id, []).append(ProjectRef(id=key_id, name=key_name or ""))

    folders_by_project: Dict[str, List[ProjectFolderSummary]] = {}
    if with_folders and ids:
        for folder in db.query(Folder).filter(scope.of(Folder), Folder.project_id.in_(ids)).all():
            folders_by_project.setdefault(folder.project_id, []).append(ProjectFolderSummary(
                id=folder.id, name=folder.name, job_count=jobs_by_folder.get(folder.id, 0)))
        for folders in folders_by_project.values():
            folders.sort(key=lambda f: name_key(f.name))  # accent-insensitive, like the keys

    projects = sorted(projects, key=lambda p: p.name_key)
    projects.sort(key=lambda p: stats[p.id]["last_job_at"] or datetime.min, reverse=True)

    summaries = []
    for p in projects:
        fields = dict(
            id=p.id, name=p.name, description=p.description, archived=p.archived_at is not None,
            folder_count=folders_total.get(p.id, 0), api_keys=keys_by_project.get(p.id, []), **stats[p.id],
        )
        if with_folders:
            fields["folders"] = folders_by_project.get(p.id, [])
        summaries.append(ProjectSummary(**fields))
    return summaries


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    response_model_exclude_unset=True,
    summary="Listar projetos com contagens, limites e uso",
)
async def list_projects(
    include: Optional[str] = Query(None, description="`folders` inclui as pastas de cada projeto"),
    scope: Scope = Depends(visible(Project, "projects.read")),
    db: Session = Depends(get_db),
):
    """
    Os projetos do usuário, com contagens de jobs MAIN e `folder_count`, os mais
    recentes primeiro (`last_job_at` desc, depois nome). `?include=folders` traz as
    pastas de cada projeto, com contagem.

    `limits` são os da instalação (`0` = sem limite) e `usage.projects` é quantos
    projetos do usuário contam para o `PROJECT_LIMIT`, arquivados inclusive.
    """
    # One declaration, visible(Project); the counts read the same principal's jobs,
    # keys and folders through `scope.of(...)` (today the same owner filter).
    projects = db.query(Project).filter(scope.predicate).all()
    return ProjectListResponse(
        projects=summarize(db, scope, projects, _wants_folders(include)),
        limits=_limits(),
        usage=ProjectUsage(projects=count_projects(db, scope.user.id)),
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectDetailResponse,
    response_model_exclude_unset=True,
    summary="Projeto com limites e uso",
)
async def get_project(
    include: Optional[str] = Query(None, description="`folders` inclui as pastas do projeto"),
    project: Project = Depends(authorized(Project, "projects.read")),
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    O resumo do projeto (o mesmo item de `GET /projects`), os `limits` da instalação
    e o uso: `usage.folders` são as pastas do projeto, `usage.projects` os projetos
    do usuário que chama. Com `limits` em `0` (sem limite), o uso vem do mesmo jeito.
    Projeto alheio ou inexistente: 404.
    """
    scope = Scope(predicate=Project.id == project.id, user=user, permission="projects.read")
    summary = summarize(db, scope, [project], _wants_folders(include))[0]
    return ProjectDetailResponse(
        project=summary,
        limits=_limits(),
        usage=ProjectUsage(projects=count_projects(db, user.id), folders=summary.folder_count),
    )
