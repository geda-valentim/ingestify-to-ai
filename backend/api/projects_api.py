"""
Projects and folders on the API side (spec 0003).

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
from typing import Optional, Tuple

from fastapi import Form, HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.models import Folder, Job, JobStatus as DBJobStatus, Project, User
from shared.projects import (
    DB_UNAVAILABLE_DETAIL,
    InvalidNameError,
    find_project,
    get_or_create_folder,
    get_or_create_project,
    validate_name,
)
from shared.schemas import UploadFolderInfo, UploadProjectInfo

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
PROJECT_NOT_FOUND_DETAIL = "Projeto não encontrado"
FOLDER_NOT_FOUND_DETAIL = "Pasta não encontrada"
FOLDER_NOT_IN_PROJECT_DETAIL = "A pasta não pertence ao projeto informado"
PROJECT_ARCHIVED_DETAIL = "Projeto arquivado"

PROJECT_FORM_DESCRIPTION = (
    "Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). "
    "É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto."
)
PROJECT_ID_FORM_DESCRIPTION = "ID de um projeto existente (alternativa a 'project'; nunca cria)."
FOLDER_FORM_DESCRIPTION = "Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/')."
FOLDER_ID_FORM_DESCRIPTION = "ID de uma pasta existente do projeto (alternativa a 'folder')."


class LocationError(HTTPException):
    """An HTTPException that also carries a machine-readable code (used by /images/*)."""

    def __init__(self, status_code: int, error_code: str, detail: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


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


# ---------------------------------------------------------------------------
# Ownership (404 for "does not exist" and "not yours" alike)
# ---------------------------------------------------------------------------

def owned_project_or_404(db: Session, project_id: str, user: User) -> Project:
    project = db.get(Project, str(project_id)) if project_id else None
    if project is None or project.user_id != user.id:
        raise LocationError(404, "PROJECT_NOT_FOUND", PROJECT_NOT_FOUND_DETAIL)
    return project


def owned_folder_or_404(db: Session, folder_id: str, user: User) -> Folder:
    folder = db.get(Folder, str(folder_id)) if folder_id else None
    if folder is None or folder.user_id != user.id:
        raise LocationError(404, "FOLDER_NOT_FOUND", FOLDER_NOT_FOUND_DETAIL)
    return folder


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
    return plan_upload_location(db, user, api_key, parsed)


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

def find_duplicate_job(db: Session, user_id: str, checksum: str, location: UploadLocation) -> Tuple[Optional[Job], Optional[str]]:
    """
    A non-failed MAIN job with the same checksum in the same project, if any.

    Returns:
        (job in this project or None, message for a NEW job when the file was
        already processed in another project of the user, else None)
    """
    base = db.query(Job).filter(
        Job.user_id == user_id,
        Job.file_checksum == checksum,
        Job.job_type == "MAIN",
        # A failed job must not swallow a resubmission: sending the file again is the retry
        Job.status != DBJobStatus.FAILED,
    )
    same = base.filter(Job.project_id == location.project_id).first()
    if same is not None:
        return same, None

    other = base.filter(or_(Job.project_id != location.project_id, Job.project_id.is_(None))).first()
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
