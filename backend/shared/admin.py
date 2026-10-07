"""
Who is an administrator, and how one is made.

A user is an admin if the `users.is_admin` column is true, OR they are the
installation's root user (spec 0019, `users.root_slot`), OR their id is listed in
ADMIN_USER_IDS (comma-separated). This is the single rule for the /admin routes,
for `is_admin` in /auth/me, for the IAM bootstrap (spec 0014) and for anything else
that needs to know. Root stays an admin even if its `is_admin` column is cleared.
"""

from typing import Optional, Set

from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.models import ROOT_SLOT, User


def admin_user_ids(settings=None) -> Set[str]:
    """User ids granted admin through ADMIN_USER_IDS"""
    settings = settings or get_settings()
    return {uid.strip() for uid in (settings.admin_user_ids or "").split(",") if uid.strip()}


def is_effective_admin(user, settings=None) -> bool:
    """True if the user is an admin by the column, as root, or by ADMIN_USER_IDS"""
    if user is None:
        return False
    return (
        getattr(user, "is_admin", False) is True
        or getattr(user, "root_slot", None) == ROOT_SLOT
        or str(user.id) in admin_user_ids(settings)
    )


class AdminPromotionError(Exception):
    """The identifier does not name exactly one user unambiguously"""


def find_user_to_promote(db: Session, *, email: Optional[str] = None, user_id: Optional[str] = None) -> User:
    """
    The one user an operator means by --email or --id.

    Refuses when another account's *username* equals the email: usernames may
    contain "@", so someone could register the username "ops@corp.com" hoping the
    operator promotes "ops@corp.com" and a lookup matches them instead.
    """
    if (email is None) == (user_id is None):
        raise AdminPromotionError("Pass exactly one of --email or --id.")

    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise AdminPromotionError(f"No user has id {user_id}.")
        return user

    user = db.query(User).filter(User.email == email).first()
    lookalikes = db.query(User).filter(User.username == email).all()
    lookalikes = [u for u in lookalikes if user is None or u.id != user.id]
    if lookalikes:
        others = ", ".join(f"{u.id} ({u.email})" for u in lookalikes)
        raise AdminPromotionError(
            f"Refusing: the email {email!r} is also the username of another account: {others}. "
            "Check who is who, then promote with --id."
        )
    if not user:
        raise AdminPromotionError(f"No user has the email {email!r}.")
    return user
