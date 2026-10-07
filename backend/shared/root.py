"""
The installation's root user (spec 0019).

The first account registered in an installation without root becomes root: the
single, app-irrevocable bootstrap identity of the IAM (spec 0014). `users.root_slot`
holds 1 for root and NULL for everyone else; its unique index is the race guard, so
two simultaneous first registrations yield exactly one root.

In production the root can only be claimed with ROOT_SETUP_TOKEN; elsewhere the token
is optional, and required whenever it is configured.
"""

import hmac
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.models import ROOT_SLOT, AdminAudit, User


class RootError(Exception):
    """A root rule refused the request; `code` is the API error code"""

    def __init__(self, code: str, status: int, message: str):
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


def root_exists(db: Session) -> bool:
    return db.query(User.id).filter(User.root_slot == ROOT_SLOT).first() is not None


def root_pending(db: Session) -> bool:
    """
    True only for a brand-new installation: no root and no users at all.

    An installation that had users before spec 0019 has no root either, but its next
    registration must stay a plain account: root is then designated by an operator
    with `scripts/make_admin.py --root` (spec 0019 §6).
    """
    return db.query(User.id).first() is None


def _configured_token(settings) -> str:
    """ROOT_SETUP_TOKEN without surrounding whitespace; blank means unset"""
    return (settings.root_setup_token or "").strip()


def _is_production(settings) -> bool:
    return settings.environment.strip().lower() == "production"


def setup_token_required(settings=None) -> bool:
    """Whether claiming root needs a token (production always; elsewhere if one is set)"""
    settings = settings or get_settings()
    return _is_production(settings) or bool(_configured_token(settings))


def check_setup_token(token: Optional[str], settings=None) -> None:
    """Raise RootError unless `token` may claim root under the current settings"""
    settings = settings or get_settings()
    expected = _configured_token(settings)
    if not expected:
        if _is_production(settings):
            raise RootError(
                "ROOT_SETUP_TOKEN_REQUIRED", 403,
                "This installation has no root user yet. Set ROOT_SETUP_TOKEN on the "
                "server to create it.",
            )
        return
    if not token or not hmac.compare_digest(token.strip().encode(), expected.encode()):
        raise RootError(
            "ROOT_SETUP_TOKEN_INVALID", 403,
            "Missing or invalid setup token.",
        )


def create_user(db: Session, user: User, *, setup_token: Optional[str], ip: Optional[str] = None) -> User:
    """
    Persist a newly registered user, as root when the installation is brand new.

    The caller has already checked email/username uniqueness and must turn an
    IntegrityError raised here (a concurrent duplicate email/username) into a 400.
    A lost race for the root slot falls back to a plain user, also when the loser
    sent no token: once someone else holds root the token is irrelevant.
    """
    if root_pending(db):
        try:
            check_setup_token(setup_token)
        except RootError:
            db.rollback()  # fresh snapshot: a rival may have just created the first user
            if root_pending(db):
                raise
        else:
            user.is_admin = True
            user.root_slot = ROOT_SLOT
            db.add(user)
            try:
                db.flush()
                db.add(AdminAudit(
                    actor_user_id=user.id, auth_method="jwt", ip=ip,
                    action="platform.root.created", target_type="user", target_id=user.id,
                    after={"username": user.username, "email": user.email},
                ))
                db.commit()
                db.refresh(user)
                return user
            except IntegrityError:
                db.rollback()
                if not root_exists(db):
                    raise  # an email/username race, not the root slot
                user = User(
                    email=user.email, username=user.username,
                    hashed_password=user.hashed_password, is_active=True,
                )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def refuse_root_change(user: User, change) -> None:
    """
    Raise RootError if `change` (anything with the new `is_active` and `is_admin`)
    would deactivate root or clear its admin flag.
    """
    if user.is_root and (not change.is_active or not change.is_admin):
        raise RootError(
            "ROOT_IMMUTABLE", 409,
            "The root user cannot be deactivated or lose admin access.",
        )
