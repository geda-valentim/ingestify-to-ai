"""Human control/IAM requires JWT; host identities remain separate."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from shared.auth import get_current_active_user
from shared.database import get_db
from shared.access import policy
from shared.admin import is_effective_admin
from shared.models import Engine


def access_session(
    request: Request,
    user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if request.headers.get("x-api-key") or not request.headers.get(
        "authorization", ""
    ).lower().startswith("bearer "):
        raise HTTPException(403, detail={"code": "LOGIN_SESSION_REQUIRED"})
    if not is_effective_admin(user) and not policy.navigation(db, user)["permissions"]:
        raise HTTPException(403, detail={"code": "ACCESS_DENIED"})
    return user


def scoped_engine(db, id, actor, feature=None):
    e = db.query(Engine).filter((Engine.id == id) | (Engine.slug == id)).first()
    if not e or not policy.allowed(
        db, actor, "engines.read", engine=e, feature=feature
    ):
        raise HTTPException(404, detail={"code": "ENGINE_NOT_FOUND"})
    return e


def scoped_features(db, e, actor, features):
    return [
        f
        for f in features
        if policy.allowed(db, actor, "engines.read", engine=e, feature=f)
    ]
