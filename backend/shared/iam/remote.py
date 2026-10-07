"""
`engines.remote.use`: may this user's work be placed on a remote (paid) engine?
(spec 0014 §4.6)

A route with `remote_allowed_for = 'admins'` (the ENUM is unchanged, no ALTER)
now means "requires `engines.remote.use`"; `'all'` lets everyone through. The
permission is decided twice:

- at `submit()` / `place_now()`, to record `JobDispatch.remote_allowed`: an
  optimization, so the dispatcher never considers remote executors for someone
  who never had the permission;
- by the dispatcher, once per user per tick, before every remote placement on an
  `admins` route: a revocation reaches the items already in the backlog (CA9).

Both go through `shared.iam.decide.can`, so they honour IAM_MODE: `off` is the
legacy rule (`is_effective_admin` of the user), `enforce` adds bindings of
`platform_admin` / `remote_engine_user` and drops inactive users.
"""

from typing import Optional

from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.iam.decide import can, legacy_allows
from shared.models import User

REMOTE_USE = "engines.remote.use"


def can_use_remote(user: Optional[User], *, db: Optional[Session] = None, session_factory=None,
                   mode: Optional[str] = None) -> bool:
    """
    `iam.can(user, "engines.remote.use")` for callers without a request Decider
    (submit paths of the API and workers). Without `db`, a session is opened from
    `session_factory` (default `shared.database.SessionLocal`) only when the mode
    has to read bindings: `off` decides from the user row already in hand.
    """
    if user is None:
        return False
    mode = mode or get_settings().iam_mode
    if db is not None:
        return can(db, user, REMOTE_USE, mode=mode)
    if mode == "off":
        # A read permission: nothing to audit, and the legacy rule needs no query.
        return legacy_allows(None, user, REMOTE_USE)
    if session_factory is None:
        from shared import database
        session_factory = database.SessionLocal
    with session_factory() as s:
        return can(s, user, REMOTE_USE, mode=mode)


def can_use_remote_by_id(db: Session, user_id: Optional[str], *, mode: Optional[str] = None) -> bool:
    """
    The dispatcher's check for `JobDispatch.user_id`: the user's primary-key
    lookup, plus (shadow/enforce) the indexed bindings query. No user, no remote.
    """
    if not user_id:
        return False
    user = db.get(User, str(user_id))
    return can_use_remote(user, db=db, mode=mode)
