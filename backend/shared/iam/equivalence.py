"""
Offline equivalence of the data decisions, legacy vs IAM (spec 0014 CA3, §4.11 step 3).

For every (user, resource) pair of a database — MAIN jobs, child jobs known
through `pages.page_job_id` or `parent_job_id`, projects, folders and API keys —
this compares, for `read`, `update` and `delete`:

- **legacy**: the owner rules as they stood before 0014 (`api/deps.py` and the
  inline `APIKey.user_id == current_user.id` lookups of `apikey_routes.py` at the
  merge-base), kept below as a **frozen copy**. It must not import
  `shared.iam.ownership`: comparing that module with itself proves nothing.
- **iam**: `Decider.decide(principal, "<family>.<action>", resource)`, with the
  resource built exactly as `api.iam_deps.authorized()` builds it.

Any divergence is a gate failure: `enforce` is not switched on until a run against
the dev snapshot is clean (§4.11 step 3). The CLI is `scripts/iam_equivalence.py`;
CI runs `run()` against the SQLite fixture of `tests/test_iam_equivalence.py`.

Redis: offline there is no Redis, so both sides receive the same `redis_status`
(parent link of SPLIT/MERGE jobs) and `owner_matches` (fallback for jobs MySQL
does not know); by default both answer "unknown". Absent data never authorizes,
on either side.

There is no datalake table in this codebase yet, so datalakes are not walked.
"""

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.iam.decide import Decider, JobRef, principal_for_user
from shared.iam.ownership import JobAccess
from shared.models import APIKey, Folder, Job, Page, Project, User

ACTIONS = ("read", "update", "delete")

RedisStatus = Callable[[str], Optional[dict]]
RedisOwnerMatches = Callable[[str, str], bool]


def _no_redis_status(job_id: str) -> Optional[dict]:
    return None


def _no_redis_owner(job_id: str, user_id: str) -> bool:
    return False


# ============================================
# Frozen legacy copy (api/deps.py and apikey_routes.py at merge-base 3dc5bf2)
# ============================================

_LEGACY_MAX_PARENT_CHAIN_DEPTH = 5


def _legacy_resolve_owner_id(db: Session, job: Optional[Job]) -> Optional[str]:
    current = job
    visited = set()
    depth = 0

    while current is not None and depth < _LEGACY_MAX_PARENT_CHAIN_DEPTH:
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


def _legacy_find_parent_job_in_db(db: Session, job_id: str, redis_status: RedisStatus) -> Optional[Job]:
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


def legacy_job_allowed(db: Session, job_id: str, user: User, redis_status: RedisStatus,
                       owner_matches: RedisOwnerMatches) -> bool:
    """`resolve_owned_job` before 0014, as a boolean (404 → False)."""
    db_job = db.query(Job).filter(Job.id == job_id).first()

    if db_job is not None:
        owner_id = _legacy_resolve_owner_id(db, db_job)
        return owner_id is not None and owner_id == user.id

    parent_job = _legacy_find_parent_job_in_db(db, job_id, redis_status)
    if parent_job is not None:
        owner_id = _legacy_resolve_owner_id(db, parent_job)
        return owner_id is not None and owner_id == user.id

    # MySQL does not know the job: only a positive Redis match authorizes.
    return bool(owner_matches(job_id, user.id))


def legacy_project_allowed(db: Session, project_id: str, user: User) -> bool:
    project = db.get(Project, str(project_id)) if project_id else None
    return not (project is None or project.user_id is None or project.user_id != user.id)


def legacy_folder_allowed(db: Session, folder_id: str, user: User) -> bool:
    folder = db.get(Folder, str(folder_id)) if folder_id else None
    return not (folder is None or folder.user_id is None or folder.user_id != user.id)


def legacy_api_key_allowed(db: Session, key_id: str, user: User) -> bool:
    key = db.query(APIKey).filter(APIKey.id == str(key_id), APIKey.user_id == user.id).first()
    return key is not None


def legacy_active(user: User) -> bool:
    """`get_current_active_user` refused an inactive user before any owner check."""
    return bool(user.is_active)


# ============================================
# Comparison
# ============================================

@dataclass(frozen=True)
class Divergence:
    user_id: str
    kind: str  # job | project | folder | api_key
    resource_id: str
    permission: str
    legacy: bool
    iam: bool

    def __str__(self):
        return (f"user={self.user_id} {self.kind}={self.resource_id} permission={self.permission} "
                f"legacy={self.legacy} iam={self.iam}")


@dataclass
class Report:
    pairs: int
    decisions: int
    divergences: List[Divergence]

    @property
    def clean(self) -> bool:
        return not self.divergences


def _job_ids(db: Session, extra_job_ids: Iterable[str]) -> List[str]:
    """MAIN jobs (rows of `jobs`), child jobs known through `pages`, and extras."""
    ids = {row[0] for row in db.query(Job.id)}
    ids |= {row[0] for row in db.query(Page.page_job_id).filter(Page.page_job_id.isnot(None))}
    ids |= set(extra_job_ids)
    return sorted(ids)


# API keys have one mutation permission (`api_keys.manage`) for update and delete.
_API_KEY_PERMISSION = {"read": "api_keys.read", "update": "api_keys.manage", "delete": "api_keys.manage"}


def run(
    db: Session,
    *,
    redis_status: RedisStatus = _no_redis_status,
    owner_matches: RedisOwnerMatches = _no_redis_owner,
    extra_job_ids: Sequence[str] = (),
    user_ids: Optional[Sequence[str]] = None,
) -> Report:
    """Every (user, resource, action) decision, legacy against IAM."""
    from shared.iam import ownership

    users_q = db.query(User).order_by(User.id)
    if user_ids:
        users_q = users_q.filter(User.id.in_(list(user_ids)))
    users = users_q.all()

    job_ids = _job_ids(db, extra_job_ids)
    project_ids = sorted(row[0] for row in db.query(Project.id))
    folder_ids = sorted(row[0] for row in db.query(Folder.id))
    key_ids = sorted(row[0] for row in db.query(APIKey.id))

    def job_access(s: Session, job_id: str, user_id: Optional[str]) -> JobAccess:
        return ownership.job_access(s, job_id, user_id, redis_status=redis_status, owner_matches=owner_matches)

    divergences: List[Divergence] = []
    pairs = decisions = 0

    for user in users:
        # One Decider per user, as one request would have; no bindings are read
        # for data permissions.
        decider = Decider(db, job_access=job_access)
        principal = principal_for_user(user)
        active = legacy_active(user)

        def compare(kind, resource_id, legacy_ok, resource, permission_of):
            nonlocal pairs, decisions
            pairs += 1
            legacy = active and legacy_ok
            for action in ACTIONS:
                permission = permission_of(action)
                iam = decider.decide(principal, permission, resource).allow
                decisions += 1
                if legacy != iam:
                    divergences.append(Divergence(str(user.id), kind, str(resource_id), permission, legacy, iam))

        for job_id in job_ids:
            compare("job", job_id, legacy_job_allowed(db, job_id, user, redis_status, owner_matches),
                    JobRef(job_id), lambda a: f"jobs.{a}")
        for project_id in project_ids:
            compare("project", project_id, legacy_project_allowed(db, project_id, user),
                    db.get(Project, project_id), lambda a: f"projects.{a}")
        for folder_id in folder_ids:
            compare("folder", folder_id, legacy_folder_allowed(db, folder_id, user),
                    db.get(Folder, folder_id), lambda a: f"folders.{a}")
        for key_id in key_ids:
            compare("api_key", key_id, legacy_api_key_allowed(db, key_id, user),
                    db.get(APIKey, key_id), _API_KEY_PERMISSION.get)

    return Report(pairs=pairs, decisions=decisions, divergences=divergences)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """0 clean, 1 divergences, 2 could not run."""
    parser = argparse.ArgumentParser(
        description="Compare legacy and IAM data decisions for every (user, resource) pair (spec 0014 CA3)."
    )
    parser.add_argument("--db-url", help="SQLAlchemy URL of the dump (default: DATABASE_URL of the settings)")
    parser.add_argument("--user", action="append", dest="users", help="Only this user id (repeatable)")
    parser.add_argument("--max-print", type=int, default=50, help="Divergences to print (default 50)")
    args = parser.parse_args(argv)

    url = args.db_url
    if not url:
        from shared.config import get_settings

        url = get_settings().database_url
    try:
        engine = create_engine(url)
        db = sessionmaker(bind=engine)()
    except Exception as e:
        print(f"iam_equivalence: cannot open {url!r}: {e}", file=sys.stderr)
        return 2

    try:
        report = run(db, user_ids=args.users)
    finally:
        db.close()
        engine.dispose()

    for d in report.divergences[: args.max_print]:
        print(f"DIVERGENCE {d}")
    if len(report.divergences) > args.max_print:
        print(f"... and {len(report.divergences) - args.max_print} more")
    print(f"iam_equivalence: {report.pairs} pairs, {report.decisions} decisions, "
          f"{len(report.divergences)} divergences")
    return 0 if report.clean else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
