"""Read registration policy from the database on every request, without a cache."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.models import PlatformSettings


def signup_enabled(db: Session) -> bool:
    row = db.query(PlatformSettings.signup_enabled).filter(PlatformSettings.id == 1).first()
    # Preserve existing installations' open registration until an admin changes it.
    # Database errors propagate: an unavailable policy store never opens signup.
    return bool(row[0]) if row is not None else True


def set_signup_enabled(db: Session, enabled: bool) -> None:
    query = db.query(PlatformSettings).filter(PlatformSettings.id == 1)
    if not query.update({PlatformSettings.signup_enabled: enabled}, synchronize_session=False):
        try:
            with db.begin_nested():
                db.add(PlatformSettings(id=1, signup_enabled=enabled))
                db.flush()
        except IntegrityError:
            # Another administrator created the singleton in the meantime.
            query.update({PlatformSettings.signup_enabled: enabled}, synchronize_session=False)
    db.commit()
