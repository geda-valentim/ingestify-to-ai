"""
Read-only view of every user for platform administrators: who exists, what each
one uses and which API keys each one holds (GET /admin/users*).

Everything here only reads. The list runs a fixed number of queries whatever the
number of users: one per aggregated table, grouped by user_id. Usage comes from
the `jobs` table, MAIN jobs only (the rows GET /jobs and GET /projects count), and
job statuses use the API's names (GET /jobs: `pending` is `queued`). Key hashes are
never read into a response.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from shared.admin import is_effective_admin
from shared.iam import bindings as iam_bindings
from shared.iam import catalog
from shared.iam.models import IamBinding
from shared.models import APIKey, Folder, Job, JobStatus, Project, User

SORT_FIELDS = ("created_at", "last_job_at", "jobs_total", "bytes_uploaded")
DEFAULT_SORT = "last_job_at"
RECENT_DAYS = 30


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


# Same names as GET /jobs (api/routes.py `_DB_TO_API_STATUS`).
API_STATUS = {
    JobStatus.PENDING: "queued",
    JobStatus.PROCESSING: "processing",
    JobStatus.COMPLETED: "completed",
    JobStatus.FAILED: "failed",
    JobStatus.CANCELLED: "cancelled",
    JobStatus.PARTIAL: "partial",
}


def _status(value) -> str:
    return API_STATUS.get(value, getattr(value, "value", value) or "unknown")


# A user's job, as GET /jobs and the project counts see it.
_MAIN = Job.job_type == "MAIN"


def _top_level_jobs(db: Session):
    return db.query(Job).filter(_MAIN)


def _job_totals(db: Session, user_ids=None) -> Dict[Optional[str], dict]:
    """{user_id: {jobs_total, jobs_by_status, bytes_uploaded, pages_total, last_job_at}}"""
    q = db.query(
        Job.user_id,
        Job.status,
        func.count(Job.id),
        func.coalesce(func.sum(Job.file_size_bytes), 0),
        func.coalesce(func.sum(Job.total_pages), 0),
        func.max(Job.created_at),
    ).filter(_MAIN)
    if user_ids is not None:
        q = q.filter(Job.user_id.in_(list(user_ids)))
    totals: Dict[Optional[str], dict] = {}
    for user_id, status, count, size, pages, last in q.group_by(Job.user_id, Job.status):
        t = totals.setdefault(user_id, {
            "jobs_total": 0, "jobs_by_status": {}, "bytes_uploaded": 0, "pages_total": 0, "last_job_at": None,
        })
        t["jobs_total"] += int(count)
        name = _status(status)
        t["jobs_by_status"][name] = t["jobs_by_status"].get(name, 0) + int(count)
        t["bytes_uploaded"] += int(size or 0)
        t["pages_total"] += int(pages or 0)
        if last and (t["last_job_at"] is None or last > t["last_job_at"]):
            t["last_job_at"] = last
    return totals


def _key_totals(db: Session, now: datetime, user_ids=None) -> Dict[str, Tuple[int, Optional[datetime]]]:
    """{user_id: (usable keys: active and not expired, latest last_used_at over all keys)}"""
    usable = and_(APIKey.is_active.is_(True), or_(APIKey.expires_at.is_(None), APIKey.expires_at > now))
    q = db.query(APIKey.user_id, func.sum(case((usable, 1), else_=0)), func.max(APIKey.last_used_at))
    if user_ids is not None:
        q = q.filter(APIKey.user_id.in_(list(user_ids)))
    return {uid: (int(n or 0), last) for uid, n, last in q.group_by(APIKey.user_id)}


def _project_totals(db: Session, user_ids=None) -> Dict[str, int]:
    q = db.query(Project.user_id, func.count(Project.id))
    if user_ids is not None:
        q = q.filter(Project.user_id.in_(list(user_ids)))
    return {uid: int(n) for uid, n in q.group_by(Project.user_id)}


def _summary(user: User, jobs: dict, keys: tuple, projects: int) -> dict:
    jobs = jobs or {}
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": bool(user.is_active),
        "is_admin": is_effective_admin(user),
        "is_root": user.is_root,
        "created_at": _iso(user.created_at),
        "api_keys_active": keys[0],
        "projects_total": projects,
        "jobs_total": jobs.get("jobs_total", 0),
        "jobs_by_status": jobs.get("jobs_by_status", {}),
        "bytes_uploaded": jobs.get("bytes_uploaded", 0),
        "pages_total": jobs.get("pages_total", 0),
        "last_job_at": _iso(jobs.get("last_job_at")),
        "last_api_key_used_at": _iso(keys[1]),
    }


def list_users(
    db: Session,
    *,
    q: Optional[str] = None,
    sort: str = DEFAULT_SORT,
    descending: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Every user (active or not) with a usage summary, filtered, sorted and paginated."""
    if sort not in SORT_FIELDS:
        raise ValueError(f"sort must be one of {SORT_FIELDS}")
    users_q = db.query(User)
    needle = (q or "").strip().lower()
    if needle:
        # autoescape: "%" and "_" in the search are literal characters.
        users_q = users_q.filter(or_(
            func.lower(User.email).contains(needle, autoescape=True),
            func.lower(User.username).contains(needle, autoescape=True),
        ))
    users = users_q.all()

    # One GROUP BY per table, whatever the number of users. A search narrows them
    # to the matching users (still one query each); without one, orphaned jobs
    # (user_id NULL) are counted too.
    ids = [u.id for u in users] if needle else None
    jobs = _job_totals(db, ids) if ids != [] else {}
    keys = _key_totals(db, datetime.utcnow(), ids) if ids != [] else {}
    projects = _project_totals(db, ids) if ids != [] else {}

    items = [_summary(u, jobs.get(u.id), keys.get(u.id, (0, None)), projects.get(u.id, 0)) for u in users]
    # A user without the field (no job yet) goes last in either direction.
    present = [i for i in items if i[sort] is not None]
    missing = [i for i in items if i[sort] is None]
    present.sort(key=lambda i: (i[sort], i["id"]), reverse=descending)
    items = present + sorted(missing, key=lambda i: i["id"])

    orphans = jobs.get(None, {}).get("jobs_total", 0) if not needle else 0
    return {
        "total": len(items),
        "orphan_jobs": orphans,
        "items": items[offset:offset + limit],
    }


def _usage(db: Session, user_id: str, now: datetime) -> dict:
    by_source = {
        (source or "unknown"): int(n)
        for source, n in _top_level_jobs(db)
        .filter(Job.user_id == user_id)
        .with_entities(Job.source_type, func.count(Job.id))
        .group_by(Job.source_type)
    }
    since = now - timedelta(days=RECENT_DAYS)
    count, size, pages = (
        _top_level_jobs(db)
        .filter(Job.user_id == user_id, Job.created_at >= since)
        .with_entities(
            func.count(Job.id),
            func.coalesce(func.sum(Job.file_size_bytes), 0),
            func.coalesce(func.sum(Job.total_pages), 0),
        )
        .one()
    )
    return {
        "by_source_type": by_source,
        "last_30_days": {"jobs": int(count or 0), "bytes": int(size or 0), "pages": int(pages or 0)},
    }


def _api_keys(db: Session, user_id: str, now: datetime) -> List[dict]:
    rows = (
        db.query(
            APIKey.id, APIKey.name, APIKey.is_active, APIKey.created_at,
            APIKey.last_used_at, APIKey.expires_at, APIKey.project_id,
        )
        .filter(APIKey.user_id == user_id)
        .order_by(APIKey.created_at.desc(), APIKey.id)
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "is_active": bool(r.is_active),
            "created_at": _iso(r.created_at),
            "last_used_at": _iso(r.last_used_at),
            "expires_at": _iso(r.expires_at),
            "expired": bool(r.expires_at and r.expires_at < now),
            "project_id": r.project_id,
        }
        for r in rows
    ]


def _projects(db: Session, user_id: str) -> List[dict]:
    projects = (
        db.query(Project.id, Project.name, Project.archived_at, Project.created_at)
        .filter(Project.user_id == user_id)
        .order_by(Project.created_at, Project.id)
        .all()
    )
    folders = dict(
        db.query(Folder.project_id, func.count(Folder.id))
        .filter(Folder.user_id == user_id)
        .group_by(Folder.project_id)
        .all()
    )
    jobs = dict(
        _top_level_jobs(db)
        .filter(Job.user_id == user_id)
        .with_entities(Job.project_id, func.count(Job.id))
        .group_by(Job.project_id)
        .all()
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "archived": p.archived_at is not None,
            "created_at": _iso(p.created_at),
            "folder_count": int(folders.get(p.id, 0)),
            "jobs_total": int(jobs.get(p.id, 0)),
        }
        for p in projects
    ]


def _bindings(db: Session, user_id: str, now: datetime, engines_viewer: Optional[str]) -> List[dict]:
    """
    The user's active bindings, as GET /admin/iam/bindings decides and shows them:
    platform rows by their own state; engines rows only when `engines_viewer` (the
    caller, with engines authority on a login session) may see them, each decided
    by the 0009 chain (`view_any`: parent delegation and owner), inactive ones left out.
    """
    platform = (
        db.query(IamBinding)
        .filter(
            IamBinding.subject_type == "user",
            IamBinding.subject_id == user_id,
            IamBinding.scope_type == "platform",
            IamBinding.role.notin_(list(catalog.ENGINE_ROLES)),
            IamBinding.condition_ref.is_(None),
            IamBinding.revoked_at.is_(None),
            IamBinding.expires_at > now,
        )
        .order_by(IamBinding.created_at.desc(), IamBinding.id)
        .all()
    )
    rows = [iam_bindings.view(b, now) for b in platform]
    if engines_viewer:
        for b in iam_bindings._visible_engine_bindings(db, engines_viewer):
            if b.subject_type == "user" and b.subject_id == user_id:
                row = iam_bindings.view_any(db, b, now)
                if row["active"]:
                    rows.append(row)
    return rows


def get_user(
    db: Session, user_id: str, now: Optional[datetime] = None, *, engines_viewer: Optional[str] = None
) -> Optional[dict]:
    """One user's summary plus keys, projects, usage and active bindings; None if absent."""
    user = db.get(User, user_id)
    if user is None:
        return None
    now = now or datetime.utcnow()
    jobs = _job_totals(db, [user.id]).get(user.id)
    keys = _key_totals(db, now, [user.id]).get(user.id, (0, None))
    projects = _projects(db, user.id)
    detail = _summary(user, jobs, keys, len(projects))
    detail.update(
        api_keys=_api_keys(db, user.id, now),
        projects=projects,
        usage=_usage(db, user.id, now),
        iam_bindings=_bindings(db, user.id, now, engines_viewer),
    )
    return detail
