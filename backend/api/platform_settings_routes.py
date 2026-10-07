"""Public signup availability and administrator-only platform policy."""
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy.orm import Session

from api.admin_routes import require_admin
from shared.database import get_db
from shared.platform_settings import signup_enabled, set_signup_enabled

router = APIRouter(tags=["Platform settings"])


class RegistrationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signup_enabled: StrictBool


@router.get("/auth/registration-settings", response_model=RegistrationSettings)
def registration_settings(response: Response, db: Session = Depends(get_db)):
    """Only the public registration policy; never exposes internal configuration."""
    response.headers["Cache-Control"] = "no-store"
    return RegistrationSettings(signup_enabled=signup_enabled(db))


@router.get("/admin/settings", response_model=RegistrationSettings)
def read_settings(response: Response, admin=Depends(require_admin), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return RegistrationSettings(signup_enabled=signup_enabled(db))


@router.patch("/admin/settings", response_model=RegistrationSettings)
def update_settings(
    body: RegistrationSettings, response: Response,
    admin=Depends(require_admin), db: Session = Depends(get_db),
):
    set_signup_enabled(db, body.signup_enabled)
    response.headers["Cache-Control"] = "no-store"
    return body
