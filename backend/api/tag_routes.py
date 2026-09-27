"""
Job tags: the shared request helpers and the two tag endpoints.

Every endpoint that creates a job (`/upload`, `/convert`, `/transcribe`,
`/images/*`) accepts tags and parses them here, so all of them validate the
same way. Listing by tag is `GET /jobs?tag=...` in routes.py.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_owned_job
from shared.auth import get_current_active_user
from shared.database import get_db
from shared.models import Job, JobTag, User
from shared.tags import MAX_TAG_LENGTH, MAX_TAGS_PER_JOB, InvalidTagsError, add_job_tags, parse_tags, set_job_tags

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tags"])

TAGS_FORM_DESCRIPTION = (
    "Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; "
    f"até {MAX_TAGS_PER_JOB} tags de até {MAX_TAG_LENGTH} caracteres. Enviar um "
    "arquivo repetido adiciona as tags ao job existente."
)


def parse_tags_or_422(raw) -> List[str]:
    try:
        return parse_tags(raw)
    except InvalidTagsError as e:
        raise HTTPException(status_code=422, detail=str(e))


def add_tags_to_existing_job(db: Session, job: Job, tags: List[str]) -> None:
    """A repeated upload returns the existing job; its new tags are merged in."""
    if not tags:
        return
    try:
        add_job_tags(job, tags)
        db.commit()
    except InvalidTagsError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.warning(f"Could not add tags to existing job {job.id}: {e}")


class TagCount(BaseModel):
    tag: str
    count: int


class TagListResponse(BaseModel):
    tags: List[TagCount]


class JobTagsUpdate(BaseModel):
    tags: List[str] = Field(..., description="A lista completa de tags do job (substitui as atuais).")


class JobTagsResponse(BaseModel):
    job_id: str
    tags: List[str]


@router.get("/tags", response_model=TagListResponse, summary="Listar as tags do usuário")
async def list_tags(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Todas as tags usadas nos jobs do usuário, com quantos jobs têm cada uma.

    Ordenadas da mais usada para a menos usada. Serve para autocompletar e
    para montar filtros; filtre a lista com `GET /jobs?tag=...`.
    """
    rows = (
        db.query(JobTag.tag, func.count(JobTag.job_id))
        .join(Job, Job.id == JobTag.job_id)
        .filter(Job.user_id == current_user.id)
        .group_by(JobTag.tag)
        .order_by(func.count(JobTag.job_id).desc(), JobTag.tag)
        .all()
    )
    return TagListResponse(tags=[TagCount(tag=tag, count=count) for tag, count in rows])


@router.put("/jobs/{job_id}/tags", response_model=JobTagsResponse, summary="Definir as tags de um job")
async def replace_job_tags(
    job_id: str,
    body: JobTagsUpdate,
    owned_job: Optional[Job] = Depends(get_owned_job),
    db: Session = Depends(get_db),
):
    """
    Substitui as tags do job pela lista enviada (`[]` remove todas).

    As tags são normalizadas como na criação: minúsculas, sem `#`, sem repetição.
    """
    if owned_job is None or str(owned_job.id) != job_id:
        # Child jobs (pages) and Redis-only jobs have no row to tag.
        raise HTTPException(status_code=404, detail="Job não encontrado")

    tags = parse_tags_or_422(body.tags)
    try:
        set_job_tags(owned_job, tags)
        db.commit()
    except InvalidTagsError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    db.refresh(owned_job)
    return JobTagsResponse(job_id=job_id, tags=owned_job.tags)
