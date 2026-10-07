"""
Who owns a resource, decided from MySQL (moved from `api/deps.py`, spec 0014 §4.4).

`api.deps` keeps its dependencies and HTTP errors and delegates here, so the API
and `shared.iam.decide` resolve ownership through one implementation.

## Child jobs (SPLIT / PAGE / MERGE)

Child jobs are **not** rows of `jobs` (workers only write `pages`). An owner is
resolved, in order, from:

1. The job's own row in `jobs` (MAIN jobs) — walking `parent_job_id` while
   `user_id` is NULL.
2. `pages.page_job_id` -> `pages.job_id` -> the MAIN job in MySQL (PAGE jobs).
3. `parent_job_id` from the Redis status, used **only** to find the parent link;
   the owner still comes from MySQL (SPLIT/MERGE jobs). Removed by 0016.
4. Last resort, only when MySQL does not know the job at all (the MySQL write
   failed during upload): the owner cached in Redis, and only on an explicit
   `owner == user.id` match.

Absent data (`user_id` NULL because of `ondelete="SET NULL"`, expired Redis
status, unknown job) **never** authorizes.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

from shared.models import Job, Page

logger = logging.getLogger(__name__)

# Maximum depth when walking MAIN -> SPLIT/PAGE/MERGE.
MAX_PARENT_CHAIN_DEPTH = 5

RedisStatus = Callable[[str], Optional[dict]]
RedisOwnerMatches = Callable[[str, str], bool]


def owns(resource, user_id: Optional[str]) -> bool:
    """A row with a `user_id` column belongs to `user_id`. NULL on either side denies."""
    owner_id = getattr(resource, "user_id", None) if resource is not None else None
    return owner_id is not None and user_id is not None and owner_id == user_id


def row_by_id(db: Session, model: type, row_id) -> Optional[object]:
    """A row by primary key; None for an empty id or a missing row."""
    if not row_id:
        return None
    return db.get(model, str(row_id))


def owned_row(db: Session, model: type, row_id, user_id: Optional[str]):
    """
    The row of `model` named `row_id` when it belongs to `user_id`, else None.

    Equivalent to the legacy `filter(Model.id == row_id, Model.user_id == user_id)`
    (missing and someone else's are the same None), for owned rows with a
    `user_id` column that callers reach by an id from a body or a job, not from a
    route path (e.g. a datalake connection named in an upload's destination).
    """
    row = row_by_id(db, model, row_id)
    return row if owns(row, user_id) else None


def resolve_owner_id(db: Session, job: Optional[Job]) -> Optional[str]:
    """
    The authoritative owner of a job in MySQL, walking `parent_job_id` while
    `user_id` is NULL. None for an orphan, a broken chain or a cycle.
    """
    current = job
    visited = set()
    depth = 0

    while current is not None and depth < MAX_PARENT_CHAIN_DEPTH:
        owner_id = current.user_id
        if owner_id is not None:
            return owner_id

        parent_job_id = current.parent_job_id
        if not parent_job_id or parent_job_id in visited:
            return None

        visited.add(current.id)
        current = db.query(Job).filter(Job.id == parent_job_id).first()
        depth += 1

    return None


def redis_job_status(job_id: str) -> Optional[dict]:
    """The Redis status, failure-tolerant (never authorizes by itself)."""
    try:
        from shared.redis_client import get_redis_client

        return get_redis_client().get_job_status(job_id)
    except Exception as e:  # pragma: no cover - Redis unavailable
        logger.warning(f"Não foi possível consultar status do job {job_id} no Redis: {e}")
        return None


def redis_owner_matches(job_id: str, user_id: str) -> bool:
    """
    Fallback used only when MySQL does not know the job. Requires an explicit
    match between the owner cached in Redis and the user; absence never authorizes.
    """
    try:
        from shared.redis_client import get_redis_client

        owner_id = get_redis_client().get_job_owner(job_id)
    except Exception as e:  # pragma: no cover - Redis unavailable
        logger.warning(f"Não foi possível consultar o dono do job {job_id} no Redis: {e}")
        return False

    return bool(owner_id) and bool(user_id) and owner_id == user_id


def find_parent_job_in_db(
    db: Session, job_id: str, redis_status: RedisStatus = redis_job_status
) -> Optional[Job]:
    """The MAIN job (in MySQL) of a child job that has no row of its own."""
    page = db.query(Page).filter(Page.page_job_id == job_id).first()
    if page is not None and page.job_id:
        parent = db.query(Job).filter(Job.id == page.job_id).first()
        if parent is not None:
            return parent

    status_data = redis_status(job_id)
    parent_job_id = status_data.get("parent_job_id") if status_data else None
    if parent_job_id:
        return db.query(Job).filter(Job.id == parent_job_id).first()

    return None


@dataclass(frozen=True)
class JobAccess:
    """
    allowed: the user owns the job.
    job: the job's own row; the MAIN row that authorized a child job; or None
         when only the Redis fallback authorized (no MySQL row at all).
    """

    allowed: bool
    job: Optional[Job]


def job_access(
    db: Session,
    job_id: str,
    user_id: Optional[str],
    *,
    redis_status: RedisStatus = redis_job_status,
    owner_matches: RedisOwnerMatches = redis_owner_matches,
) -> JobAccess:
    """Whether `user_id` owns `job_id`, exactly as `api.deps.resolve_owned_job` always did."""
    db_job = db.query(Job).filter(Job.id == job_id).first()

    if db_job is not None:
        owner_id = resolve_owner_id(db, db_job)
        # `owner_id is None` (orphan job) NEVER authorizes.
        if owner_id is not None and owner_id == user_id:
            return JobAccess(True, db_job)
        logger.warning(
            f"Acesso negado ao job {job_id} para o usuário {user_id} "
            f"(dono resolvido: {owner_id})"
        )
        return JobAccess(False, None)

    # Child job: no row of its own in MySQL, the owner comes from the MAIN job.
    parent_job = find_parent_job_in_db(db, job_id, redis_status)
    if parent_job is not None:
        owner_id = resolve_owner_id(db, parent_job)
        if owner_id is not None and owner_id == user_id:
            return JobAccess(True, parent_job)
        logger.warning(
            f"Acesso negado ao job filho {job_id} para o usuário {user_id} "
            f"(dono do job pai {parent_job.id}: {owner_id})"
        )
        return JobAccess(False, None)

    # MySQL does not know the job: only a positive Redis match authorizes.
    if user_id is not None and owner_matches(job_id, user_id):
        logger.info(
            f"Job {job_id} não existe no MySQL; acesso autorizado pelo dono registrado no Redis"
        )
        return JobAccess(True, None)

    return JobAccess(False, None)
