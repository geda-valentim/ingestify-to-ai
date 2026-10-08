"""
Projects and folders on the API side (spec 0004).

Upload location
---------------
Every endpoint that creates a job (`/upload`, `/convert`, `/transcribe`,
`/images/describe[/upload]`, `/images/ocr[/upload]`) takes the same four
fields - form fields on multipart routes, body fields on JSON routes:

| field        | meaning                                                      |
|--------------|--------------------------------------------------------------|
| `project`    | project name; get-or-add                                     |
| `project_id` | existing project; never creates                              |
| `folder`     | folder name inside the resolved project; get-or-add          |
| `folder_id`  | existing folder; must belong to the resolved project         |

The project is, in order: the one in the request; else, for a request
authenticated by API key only (no JWT), the key's bound project; else 422.
(`UPLOAD_FALLBACK_PROJECT`, empty by default, is an emergency valve.)

Handlers do it in three steps so nothing is created and nothing is written to
disk for a request that is going to fail:

1. `parse_location_or_422` - shape only (sizes, '/', exclusivity);
2. `plan_upload_location` - read-only: is there a project in the request or on
   the key? do the IDs exist and belong to the caller? (before the stream);
3. `resolve_upload_location` - get-or-add (after the stream).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Form, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from api.deps import (
    FOLDER_NOT_FOUND_DETAIL,
    PROJECT_NOT_FOUND_DETAIL,
    LocationError,
    owned_folder_or_404,
    owned_project_or_404,
)
from api.iam_deps import Scope, authorized, visible
from shared.config import get_settings
from shared.database import get_db
from shared.models import APIKey, Folder, Job, JobStatus as DBJobStatus, Project, User
from shared.projects import (
    DB_UNAVAILABLE_DETAIL,
    InvalidNameError,
    find_folder,
    find_project,
    get_or_create_folder,
    get_or_create_project,
    name_key,
    validate_name,
)
from shared.schemas import ProjectRef, UploadFolderInfo, UploadProjectInfo

logger = logging.getLogger(__name__)

PROJECT_REQUIRED_DETAIL = (
    "Informe o projeto do upload: campo 'project' (nome; é criado se não existir) ou "
    "'project_id'. Exemplo: curl -H \"X-API-Key: ...\" -F \"file=@arquivo.mp3\" "
    "-F \"project=Aulas\" .../transcribe\n"
    "Para não precisar enviar o projeto, vincule a API key a um projeto em /api-keys."
)
KEY_PROJECT_GONE_DETAIL = (
    "O projeto vinculado a esta API key não existe mais. Informe o campo 'project' "
    "(nome; é criado se não existir) ou 'project_id', ou vincule a key a outro projeto em /api-keys."
)
FOLDER_NOT_IN_PROJECT_DETAIL = "A pasta não pertence ao projeto informado"
PROJECT_ARCHIVED_DETAIL = "Projeto arquivado"

PROJECT_FORM_DESCRIPTION = (
    "Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). "
    "É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto."
)
PROJECT_ID_FORM_DESCRIPTION = "ID de um projeto existente (alternativa a 'project'; nunca cria)."
FOLDER_FORM_DESCRIPTION = "Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/')."
FOLDER_ID_FORM_DESCRIPTION = "ID de uma pasta existente do projeto (alternativa a 'folder')."


# ---------------------------------------------------------------------------
# 1. Shape
# ---------------------------------------------------------------------------

@dataclass
class LocationFields:
    """The four raw fields, as received."""
    project: Optional[str] = None
    project_id: Optional[str] = None
    folder: Optional[str] = None
    folder_id: Optional[str] = None


def upload_location_form(
    project: Optional[str] = Form(None, description=PROJECT_FORM_DESCRIPTION),
    project_id: Optional[str] = Form(None, description=PROJECT_ID_FORM_DESCRIPTION),
    folder: Optional[str] = Form(None, description=FOLDER_FORM_DESCRIPTION),
    folder_id: Optional[str] = Form(None, description=FOLDER_ID_FORM_DESCRIPTION),
) -> LocationFields:
    """FastAPI dependency: the location form fields of a multipart upload."""
    return LocationFields(project=project, project_id=project_id, folder=folder, folder_id=folder_id)


@dataclass
class ParsedLocation:
    project_name: Optional[str] = None
    project_id: Optional[str] = None
    folder_name: Optional[str] = None
    folder_id: Optional[str] = None


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    # `-F project=` is "absent", not "the empty name"
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def parse_location_or_422(fields: LocationFields) -> ParsedLocation:
    project = _blank_to_none(fields.project)
    project_id = _blank_to_none(fields.project_id)
    folder = _blank_to_none(fields.folder)
    folder_id = _blank_to_none(fields.folder_id)

    if project and project_id:
        raise LocationError(422, "INVALID_LOCATION", "Envie 'project' ou 'project_id', não os dois")
    if folder and folder_id:
        raise LocationError(422, "INVALID_LOCATION", "Envie 'folder' ou 'folder_id', não os dois")
    try:
        project_name = validate_name(project, "project")[0] if project else None
        folder_name = validate_name(folder, "folder")[0] if folder else None
    except InvalidNameError as e:
        raise LocationError(422, "INVALID_LOCATION", str(e))
    return ParsedLocation(project_name=project_name, project_id=project_id,
                          folder_name=folder_name, folder_id=folder_id)


def bound_project(db: Session, api_key, user: User) -> Optional[Project]:
    """The key's project when the binding is still valid (exists, same owner), else None."""
    if api_key is None or not api_key.project_id:
        return None
    project = db.get(Project, api_key.project_id)
    if project is None or project.user_id != user.id or api_key.user_id != user.id:
        return None
    return project


# ---------------------------------------------------------------------------
# 2. Read-only plan (before the upload is written to disk)
# ---------------------------------------------------------------------------

@dataclass
class UploadPlan:
    parsed: ParsedLocation
    source: str                           # "request" | "api_key" | "fallback"
    project: Optional[Project] = None     # known already (by id, key, or existing name)
    folder: Optional[Folder] = None       # known already (by id)
    fallback_name: Optional[str] = None


def plan_upload_location(db: Session, user: User, api_key, parsed: ParsedLocation) -> UploadPlan:
    """
    Decide where the upload goes without writing anything.

    Raises:
        LocationError 422: no project (request, key or fallback), archived
            project, folder of another project.
        LocationError 404: project_id / folder_id that does not exist or is not the caller's.
        LocationError 503: database error.
    """
    try:
        if parsed.project_id:
            plan = UploadPlan(parsed, "request", project=owned_project_or_404(db, parsed.project_id, user))
        elif parsed.project_name:
            plan = UploadPlan(parsed, "request",
                              project=find_project(db, user.id, validate_name(parsed.project_name)[1]))
        elif api_key is not None and api_key.project_id:
            project = bound_project(db, api_key, user)
            if project is None:
                raise LocationError(422, "PROJECT_REQUIRED", KEY_PROJECT_GONE_DETAIL)
            plan = UploadPlan(parsed, "api_key", project=project)
        elif get_settings().upload_fallback_project.strip():
            name = get_settings().upload_fallback_project
            try:
                key = validate_name(name)[1]
            except InvalidNameError as e:
                logger.error(f"UPLOAD_FALLBACK_PROJECT is invalid ({e}); answering 422")
                raise LocationError(422, "PROJECT_REQUIRED", PROJECT_REQUIRED_DETAIL)
            plan = UploadPlan(parsed, "fallback", project=find_project(db, user.id, key), fallback_name=name)
        else:
            raise LocationError(422, "PROJECT_REQUIRED", PROJECT_REQUIRED_DETAIL)

        if plan.project is not None and plan.project.archived_at is not None:
            raise LocationError(422, "PROJECT_ARCHIVED", PROJECT_ARCHIVED_DETAIL)

        if parsed.folder_id:
            folder = owned_folder_or_404(db, parsed.folder_id, user)
            if plan.project is None or folder.project_id != plan.project.id:
                raise LocationError(422, "INVALID_LOCATION", FOLDER_NOT_IN_PROJECT_DETAIL)
            plan.folder = folder
        return plan
    except (OperationalError, InterfaceError) as e:
        db.rollback()
        logger.error(f"plan_upload_location: {e}")
        raise LocationError(503, "DATABASE_UNAVAILABLE", DB_UNAVAILABLE_DETAIL)


def prepare_upload_location(db: Session, user: User, request, fields: LocationFields) -> UploadPlan:
    """Steps 1 and 2 together: parse the fields, then plan without writing."""
    parsed = parse_location_or_422(fields)
    api_key = getattr(getattr(request, "state", None), "api_key", None)
    plan = plan_upload_location(db, user, api_key, parsed)
    # Planning only reads. End that transaction before the upload is streamed:
    # otherwise its read view (and metadata locks on api_keys/projects/folders)
    # stays open for the whole stream, and the dedup query after it would read
    # the pre-stream snapshot. ORM objects in the plan are reloaded on access.
    db.rollback()
    return plan


# ---------------------------------------------------------------------------
# 3. Get-or-add (after the upload is on disk)
# ---------------------------------------------------------------------------

@dataclass
class UploadLocation:
    project: Project
    folder: Optional[Folder] = None
    project_created: bool = False
    folder_created: bool = False
    source: str = "request"
    project_id: str = field(init=False)
    folder_id: Optional[str] = field(init=False)

    def __post_init__(self):
        # Plain copies: a later commit expires the ORM objects.
        self.project_id = self.project.id
        self.folder_id = self.folder.id if self.folder is not None else None
        self._project_name = self.project.name
        self._folder_name = self.folder.name if self.folder is not None else None

    @property
    def project_name(self) -> str:
        return self._project_name

    def project_info(self) -> UploadProjectInfo:
        return UploadProjectInfo(id=self.project_id, name=self._project_name,
                                 created=self.project_created, source=self.source)

    def folder_info(self) -> Optional[UploadFolderInfo]:
        if self.folder_id is None:
            return None
        return UploadFolderInfo(id=self.folder_id, name=self._folder_name, created=self.folder_created)


def resolve_upload_location(db: Session, user: User, plan: UploadPlan, path: str = "") -> UploadLocation:
    """
    Get-or-add the project and folder the plan points at. Commits.

    Raises:
        HTTPException 422 / 503 (see shared/projects.py).
    """
    via = plan.source
    try:
        if plan.project is not None:
            project, project_created = plan.project, False
        else:
            name = plan.parsed.project_name if plan.source == "request" else plan.fallback_name
            project, project_created = get_or_create_project(db, user.id, name, origin=via)
        if plan.source == "fallback":
            logger.warning(
                f"UPLOAD_FALLBACK_PROJECT used: user={user.id} path={path} -> project "
                f"'{project.name}' ({project.id})"
            )
        if project.archived_at is not None:
            raise LocationError(422, "PROJECT_ARCHIVED", PROJECT_ARCHIVED_DETAIL)

        folder, folder_created = plan.folder, False
        if folder is not None and folder.project_id != project.id:
            raise LocationError(422, "INVALID_LOCATION", FOLDER_NOT_IN_PROJECT_DETAIL)
        if folder is None and plan.parsed.folder_name:
            folder, folder_created = get_or_create_folder(db, project, plan.parsed.folder_name, origin=via)
    except InvalidNameError as e:
        raise LocationError(422, "INVALID_LOCATION", str(e))
    except (OperationalError, InterfaceError) as e:
        db.rollback()
        logger.error(f"resolve_upload_location: {e}")
        raise LocationError(503, "DATABASE_UNAVAILABLE", DB_UNAVAILABLE_DETAIL)

    return UploadLocation(project=project, folder=folder, project_created=project_created,
                          folder_created=folder_created, source=via)


# ---------------------------------------------------------------------------
# Deduplication, scoped by project
# ---------------------------------------------------------------------------

def conversion_operation_key(docling_preset: Optional[str], image_mode: Optional[str] = None,
                             page_images: bool = False) -> str:
    """
    Dedup key of a document conversion: the operation and the options that change
    its result. The same file converted with another preset is another job; a
    vision job (describe / OCR / analyze) of the same bytes is never a duplicate.

    `image_mode` / `page_images` (image assets) enter the key only when not the
    default, so every key recorded before they existed (all `none` / false) is
    still the key of a conversion without assets.
    """
    import hashlib
    import json

    from shared.conversion_assets import normalize_options, requested_options

    payload = {"operation": "conversion", "docling_preset": docling_preset or None}
    payload.update(requested_options(*normalize_options(image_mode, page_images)))
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def save_operation_key(db: Session, job: Job, key: str) -> None:
    """
    Persist the dedup key with the job (`Job.operation_key`; no commit). Never in
    JobConfiguration.options: that is the configuration the user requested.
    """
    job.operation_key = key


def _operation_key_of(job: Job) -> Optional[str]:
    return getattr(job, "operation_key", None)


def find_duplicate_job(db: Session, user_id: str, checksum: str, location: UploadLocation,
                       transcription_profile_hash: Optional[str] = None,
                       purge_source: bool = False,
                       operation_key: Optional[str] = None,
                       assets_requested: bool = False) -> Tuple[Optional[Job], Optional[str]]:
    """
    A MAIN job with the same checksum *and the same operation* in the same project,
    if any, that did not end failed (FAILED, or PARTIAL with failed pages: sending
    the file again is the new attempt).

    The operation: a transcription is identified by its profile hash; a document
    conversion by `operation_key` (`conversion_operation_key`: the preset and the
    image-asset options). Jobs of another kind (images) never match. A job recorded
    before operation keys existed matches any conversion of the same file without
    image assets, as it did then. `assets_requested` (the request has
    `image_mode=referenced` or `page_images=true`): such a request is never
    answered by a keyless job, nor by one whose assets were already deleted.

    With `purge_source=false` (keep the original) a job whose original is already
    gone, or was asked to be deleted, is not reused: the file is processed again
    so the user keeps it (`shared.job_source.reusable_for`).

    Returns:
        (job in this project or None, message for a NEW job when the file was
        already processed in another project of the user, or in this project
        without its original, else None)
    """
    from shared.job_source import reusable_for

    base = db.query(Job).filter(
        Job.user_id == user_id,
        Job.file_checksum == checksum,
        Job.job_type == "MAIN",
        # A failed job must not swallow a resubmission: sending the file again is the retry
        Job.status.notin_([DBJobStatus.FAILED, DBJobStatus.PARTIAL]),
        # Vision jobs (describe, OCR, analyze, faces) are other operations on the same bytes
        or_(Job.source_type.is_(None), Job.source_type != "image"),
    )
    # Media results are reusable only with the same durable processing profile.
    # A legacy NULL profile must not swallow a new request for speaker labels.
    if transcription_profile_hash is not None:
        base = base.filter(Job.transcription_profile_hash == transcription_profile_hash,
                           Job.status != DBJobStatus.CANCELLED)
    else:
        # A document conversion is never answered by a transcription of the same file
        base = base.filter(Job.transcription_profile_hash.is_(None))

    plain = not assets_requested

    def same_operation(job: Job) -> bool:
        if operation_key is None:
            return True
        recorded = _operation_key_of(job)
        if recorded is None:
            # Recorded before operation keys: a conversion without image assets
            return plain
        if recorded != operation_key:
            return False
        # Image assets already deleted (purge / DELETE /jobs/{id}/source): the
        # request would get dead asset URLs, so the file is processed again
        return plain or getattr(job, "assets_deleted_at", None) is None
    candidates = [job for job in base.filter(Job.project_id == location.project_id)
                  .order_by(Job.created_at.desc()).all() if same_operation(job)]
    same = next((job for job in candidates if reusable_for(job, purge_source)), None)
    if same is not None:
        return same, None
    if candidates:
        return None, (
            f"O arquivo original do job {candidates[0].id} foi (ou será) apagado; "
            f"processando de novo para manter o original"
        )

    other = next((job for job in base.filter(or_(Job.project_id != location.project_id,
                                                 Job.project_id.is_(None))).all()
                  if same_operation(job)), None)
    if other is None:
        return None, None
    other_project = db.get(Project, other.project_id) if other.project_id else None
    other_name = other_project.name if other_project is not None else "(sem projeto)"
    return None, (
        f"Arquivo já processado no projeto '{other_name}' (job {other.id}); "
        f"processando de novo em '{location.project_name}'"
    )


def existing_job_location(db: Session, job: Job, location: UploadLocation) -> dict:
    """Response fields for a duplicate: the job stays where it is (it is not moved, D5)."""
    folder = db.get(Folder, job.folder_id) if job.folder_id else None
    return {
        "project": location.project_info(),
        "folder": UploadFolderInfo(id=folder.id, name=folder.name, created=False) if folder else None,
    }


# ===========================================================================
# Read API (phase 1): GET /projects, name resolution
# ===========================================================================

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
    api_keys: List[ProjectRef] = Field(..., description="API keys bound to this project")
    folders: Optional[List[ProjectFolderSummary]] = Field(None, description="Only with ?include=folders")


class ProjectLimits(BaseModel):
    max_projects: int
    max_folders_per_project: int


class ProjectListResponse(BaseModel):
    projects: List[ProjectSummary]
    limits: ProjectLimits


class NameResolveResponse(BaseModel):
    valid: bool
    match: Optional[ProjectRef] = Field(None, description="The existing project/folder, or null if it would be created")
    error: Optional[str] = Field(None, description="Why the name is not acceptable (valid=false)")


router = APIRouter(tags=["Projects"])

_ACTIVE = (DBJobStatus.PENDING, DBJobStatus.PROCESSING)


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    response_model_exclude_unset=True,
    summary="Listar projetos com contagens",
)
async def list_projects(
    include: Optional[str] = Query(None, description="`folders` inclui as pastas de cada projeto"),
    scope: Scope = Depends(visible(Project, "projects.read")),
    db: Session = Depends(get_db),
):
    """
    Os projetos do usuário, com contagens de jobs MAIN, os mais recentes primeiro
    (`last_job_at` desc, depois nome). `?include=folders` traz as pastas de cada
    projeto, com contagem.

    As contagens vêm de um único `GROUP BY project_id, folder_id, status`.
    """
    with_folders = "folders" in {part.strip() for part in (include or "").split(",")}

    # One declaration, visible(Project); the counts read the same principal's jobs,
    # keys and folders through `scope.of(...)` (today the same owner filter).
    projects = db.query(Project).filter(scope.predicate).all()
    stats = {p.id: {"job_count": 0, "root_job_count": 0, "failed_count": 0, "active_count": 0,
                    "last_job_at": None} for p in projects}
    folder_counts: Dict[str, int] = {}

    rows = (
        db.query(Job.project_id, Job.folder_id, Job.status, func.count(Job.id), func.max(Job.created_at))
        .filter(scope.of(Job), Job.job_type == "MAIN", Job.project_id.isnot(None))
        .group_by(Job.project_id, Job.folder_id, Job.status)
        .all()
    )
    for project_id, folder_id, status, count, last in rows:
        st = stats.get(project_id)
        if st is None:
            continue  # a job pointing at a deleted project
        st["job_count"] += count
        if folder_id is None:
            st["root_job_count"] += count
        else:
            folder_counts[folder_id] = folder_counts.get(folder_id, 0) + count
        if status == DBJobStatus.FAILED:
            st["failed_count"] += count
        elif status in _ACTIVE:
            st["active_count"] += count
        if last is not None and (st["last_job_at"] is None or last > st["last_job_at"]):
            st["last_job_at"] = last

    keys_by_project: Dict[str, List[ProjectRef]] = {}
    for key_id, key_name, project_id in (
        db.query(APIKey.id, APIKey.name, APIKey.project_id)
        .filter(scope.of(APIKey), APIKey.project_id.isnot(None))
        .order_by(APIKey.name)
    ):
        keys_by_project.setdefault(project_id, []).append(ProjectRef(id=key_id, name=key_name or ""))

    folders_by_project: Dict[str, List[ProjectFolderSummary]] = {}
    if with_folders:
        for folder in db.query(Folder).filter(scope.of(Folder)).all():
            folders_by_project.setdefault(folder.project_id, []).append(ProjectFolderSummary(
                id=folder.id, name=folder.name, job_count=folder_counts.get(folder.id, 0)))
        for folders in folders_by_project.values():
            folders.sort(key=lambda f: name_key(f.name))  # accent-insensitive, like the keys

    projects.sort(key=lambda p: p.name_key)
    projects.sort(key=lambda p: stats[p.id]["last_job_at"] or datetime.min, reverse=True)

    summaries = []
    for p in projects:
        fields = dict(
            id=p.id, name=p.name, description=p.description, archived=p.archived_at is not None,
            api_keys=keys_by_project.get(p.id, []), **stats[p.id],
        )
        if with_folders:
            fields["folders"] = folders_by_project.get(p.id, [])
        summaries.append(ProjectSummary(**fields))

    settings = get_settings()
    return ProjectListResponse(
        projects=summaries,
        limits=ProjectLimits(max_projects=settings.max_projects_per_user,
                             max_folders_per_project=settings.max_folders_per_project),
    )


def _resolve(kind: str, name: str, find) -> NameResolveResponse:
    try:
        _display, key = validate_name(name, kind)
    except InvalidNameError as e:
        return NameResolveResponse(valid=False, error=str(e))
    found = find(key)
    return NameResolveResponse(valid=True, match=ProjectRef(id=found.id, name=found.name) if found else None)


@router.get(
    "/projects/resolve",
    response_model=NameResolveResponse,
    response_model_exclude_unset=True,
    summary="Resolver nome de projeto",
)
async def resolve_project_name(
    name: str = Query(..., description="O texto digitado"),
    scope: Scope = Depends(visible(Project, "projects.read")),
    db: Session = Depends(get_db),
):
    """
    Diz, sem criar nada, se `name` é um projeto existente (pela regra de
    normalização do backend: `reuniao` casa com "Reunião") ou se seria criado.

    `{"valid": true, "match": {"id", "name"}}`, `{"valid": true, "match": null}`
    ou `{"valid": false, "error": "..."}`. Sempre 200.
    """
    # `find_project`'s query, with the owner filter taken from the scope.
    return _resolve(
        "project", name,
        lambda key: db.query(Project).filter(scope.predicate, Project.name_key == key).first(),
    )


@router.get(
    "/projects/{project_id}/folders/resolve",
    response_model=NameResolveResponse,
    response_model_exclude_unset=True,
    summary="Resolver nome de pasta do projeto",
)
async def resolve_folder_name(
    name: str = Query(..., description="O texto digitado"),
    project: Project = Depends(authorized(Project, "projects.read")),
    db: Session = Depends(get_db),
):
    """Igual a `GET /projects/resolve`, para uma pasta do projeto. Projeto alheio: 404."""
    return _resolve("folder", name, lambda key: find_folder(db, project.id, key))
