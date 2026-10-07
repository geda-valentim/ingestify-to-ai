"""Project/folder maintenance and atomic movement of MAIN job metadata (0004).

Objects, results, tags and child jobs stay addressed by job ID. Authorization
comes from SQL ownership, and destination locks serialize movement with deletion.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from api.deps import (
    FOLDER_NOT_FOUND_DETAIL, PROJECT_NOT_FOUND_DETAIL, owned_folder_or_404,
)
from shared.auth import get_current_active_user
from shared.database import get_db
from shared.models import APIKey, Folder, Job, Project, User
from shared.projects import InvalidNameError, get_or_create_folder, get_or_create_project, validate_name

router = APIRouter(tags=['Projects'])


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class NameBody(StrictBody):
    name: str = Field(min_length=1, max_length=100)


class ProjectPatch(StrictBody):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=4000)
    archived: Optional[bool] = None


class LocationBody(StrictBody):
    project_id: str = Field(min_length=1, max_length=36)
    folder_id: Optional[str] = Field(None, min_length=1, max_length=36)


class MoveBody(LocationBody):
    job_ids: list[str] = Field(min_length=1, max_length=100)


def locked_project(db, project_id, user_id):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).populate_existing().with_for_update().first()
    if project is None:
        raise HTTPException(404, PROJECT_NOT_FOUND_DETAIL)
    return project


def locked_folder(db, folder_id, user_id):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user_id).populate_existing().with_for_update().first()
    if folder is None:
        raise HTTPException(404, FOLDER_NOT_FOUND_DETAIL)
    return folder


def project_ref(project):
    return {'id': project.id, 'name': project.name, 'description': project.description,
            'archived': project.archived_at is not None}


def cosmetic_name(resource, raw, kind):
    try:
        display, key = validate_name(raw, kind)
    except (InvalidNameError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from None
    if key != resource.name_key:
        raise HTTPException(422, 'O nome só pode corrigir caixa, acentos ou espaços; a identidade deve permanecer igual')
    resource.name = display


def bound_keys(db, project_id, user_id):
    return [name or key_id for key_id, name in db.query(APIKey.id, APIKey.name).filter(
        APIKey.project_id == project_id, APIKey.user_id == user_id).all()]


def ensure_active(project):
    if project.archived_at is not None:
        raise HTTPException(422, 'Projeto arquivado')


@router.post('/projects')
def create_project(body: NameBody, response: Response, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    user_id = user.id
    db.rollback()  # End the authentication snapshot before acquiring current locks.
    db.query(User).filter(User.id == user_id).with_for_update().one()
    try:
        project, created = get_or_create_project(db, user_id, body.name, origin='project_management')
    except InvalidNameError as exc:
        raise HTTPException(422, str(exc)) from None
    db.commit()
    response.status_code = 201 if created else 200
    return {**project_ref(project), 'created': created}


@router.patch('/projects/{project_id}')
def update_project(project_id: str, body: ProjectPatch, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    user_id = user.id
    db.rollback()
    project = locked_project(db, project_id, user_id)
    if 'archived' in body.model_fields_set:
        if body.archived is None:
            raise HTTPException(422, 'archived deve ser true ou false')
        if body.archived:
            names = bound_keys(db, project_id, user_id)
            if names:
                raise HTTPException(409, 'Projeto usado pelas API keys: ' + ', '.join(names))
        project.archived_at = (project.archived_at or datetime.utcnow()) if body.archived else None
    if 'name' in body.model_fields_set:
        cosmetic_name(project, body.name, 'project')
    if 'description' in body.model_fields_set:
        project.description = body.description
    db.commit()
    return project_ref(project)


@router.delete('/projects/{project_id}', status_code=204)
def delete_project(project_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    user_id = user.id
    db.rollback()
    project = locked_project(db, project_id, user_id)
    names = bound_keys(db, project_id, user_id)
    if names:
        raise HTTPException(409, 'Projeto usado pelas API keys: ' + ', '.join(names))
    if db.query(Job.id).filter(Job.project_id == project_id, Job.user_id == user_id).first():
        raise HTTPException(409, 'Projeto contém jobs; mova-os antes de excluir')
    db.query(Folder).filter(Folder.project_id == project_id, Folder.user_id == user_id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    return Response(status_code=204)


@router.post('/projects/{project_id}/folders')
def create_folder(project_id: str, body: NameBody, response: Response, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    user_id = user.id
    db.rollback()
    project = locked_project(db, project_id, user_id)
    ensure_active(project)
    try:
        folder, created = get_or_create_folder(db, project, body.name, origin='project_management')
    except InvalidNameError as exc:
        raise HTTPException(422, str(exc)) from None
    db.commit()
    response.status_code = 201 if created else 200
    return {'id': folder.id, 'name': folder.name, 'project_id': folder.project_id, 'created': created}


def folder_for_maintenance(db, folder_id, user):
    # Always lock project before folder, matching destination locks in move.
    folder = owned_folder_or_404(db, folder_id, user)
    project_id, user_id = folder.project_id, user.id
    db.rollback()
    locked_project(db, project_id, user_id)
    return locked_folder(db, folder_id, user_id)


@router.patch('/folders/{folder_id}')
def update_folder(folder_id: str, body: NameBody, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    folder = folder_for_maintenance(db, folder_id, user)
    cosmetic_name(folder, body.name, 'folder')
    db.commit()
    return {'id': folder.id, 'name': folder.name, 'project_id': folder.project_id}


@router.delete('/folders/{folder_id}', status_code=204)
def delete_folder(folder_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    user_id = user.id
    folder = folder_for_maintenance(db, folder_id, user)
    db.query(Job).filter(Job.folder_id == folder_id, Job.user_id == user_id).update(
        {'folder_id': None}, synchronize_session=False)
    db.delete(folder)
    db.commit()
    return Response(status_code=204)


def move_jobs(db, user_id, ids, body):
    db.rollback()
    project = locked_project(db, body.project_id, user_id)
    ensure_active(project)
    folder = locked_folder(db, body.folder_id, user_id) if body.folder_id else None
    if folder is not None and folder.project_id != project.id:
        raise HTTPException(422, 'A pasta não pertence ao projeto informado')
    ids = sorted(set(ids))
    jobs = db.query(Job).filter(Job.id.in_(ids), Job.user_id == user_id).order_by(Job.id).populate_existing().with_for_update().all()
    if len(jobs) != len(ids):
        raise HTTPException(404, 'Job not found')
    if any(job.job_type != 'MAIN' for job in jobs):
        raise HTTPException(422, 'Mova o job principal; os jobs filhos herdam sua localização')
    for job in jobs:
        job.project_id, job.folder_id = project.id, folder.id if folder else None
    db.commit()
    return {'job_ids': ids, 'moved': len(jobs), 'project': {'id': project.id, 'name': project.name},
            'folder': {'id': folder.id, 'name': folder.name} if folder else None}


@router.patch('/jobs/{job_id}/location')
def move_job(job_id: str, body: LocationBody, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return move_jobs(db, user.id, [job_id], body)


@router.post('/jobs/move')
def move_batch(body: MoveBody, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return move_jobs(db, user.id, body.job_ids, body)
