from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from shared.database import get_db
from shared.access import service, policy, contracts as C
from shared.access.models import EngineAttributes, ResourceScope, ExecutionRevision
from shared.engine_control.models import ControlResource
from shared.models import Engine, User
from shared import root
from api.access_deps import access_session, scoped_engine
from api.engine_control_routes import invoke
from api.iam_deps import engine_access

# 0009 routes: decided by access_session + policy; engine_access only declares them (0014 CA1).
router = APIRouter(prefix="/admin", tags=["Admin - Execution profiles and access"], dependencies=[Depends(engine_access())])


def ready():
    invoke(service.require_enabled)


@router.get("/access/me")
def me(user=Depends(access_session), db: Session = Depends(get_db)):
    return policy.navigation(db, user)


@router.get("/execution-profiles")
def profiles(user=Depends(access_session), db: Session = Depends(get_db)):
    ready()
    return invoke(service.list_profiles, db, user.id)


@router.post("/execution-profiles", status_code=201)
def create(
    body: C.ProfileCreate, user=Depends(access_session), db: Session = Depends(get_db)
):
    return invoke(service.create_profile, db, body, user.id)


@router.get("/execution-profiles/{id}")
def detail(id: str, user=Depends(access_session), db: Session = Depends(get_db)):
    ready()
    p = invoke(service.get_profile, db, id, user.id)
    return service.view(db, p, user.id, True)


@router.put("/execution-profiles/{id}")
def metadata(
    id: str,
    body: C.MetadataUpdate,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    ready()
    return invoke(service.metadata, db, id, body, user.id)


@router.post("/execution-profiles/{id}/revisions", status_code=201)
def revision(
    id: str,
    body: C.RevisionCreate,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    return invoke(service.revise, db, id, body, user.id)


@router.post("/execution-profiles/{id}/publish")
def publish(
    id: str,
    body: C.Publish,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    ready()
    return invoke(service.publish, db, id, body, user.id)


@router.post("/execution-profiles/{id}/archive")
def archive(
    id: str,
    body: C.Version,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    ready()
    return invoke(service.archive, db, id, body.version, user.id)


@router.post("/engines/{id}/runtime-profile/bind")
def bind(
    id: str, body: C.Bind, user=Depends(access_session), db: Session = Depends(get_db)
):
    e = scoped_engine(db, id, user.id, body.feature)
    return invoke(service.bind, db, e, body, user.id)


@router.post("/engines/{id}/runtime-profile/import", status_code=201)
def import_profile(
    id: str,
    body: C.ProfileCreate,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    # An import is an ordinary draft; the immutable legacy desired/applied records stay intact.
    ready()
    invoke(service.bootstrap, db, user.id)
    from shared.engine_control import service as control
    from shared.engine_control.contracts import RuntimeSettings

    e = scoped_engine(db, id, user.id, body.feature)
    old = control.latest_profile(db, e.id, body.feature)
    if not old:
        raise HTTPException(404, detail={"code": "RUNTIME_PROFILE_NOT_FOUND"})
    settings = {
        k: v for k, v in old.profile.items() if k in RuntimeSettings.model_fields
    }
    settings["warm_until"] = None
    if body.adapter_type != e.adapter_type:
        raise HTTPException(422, detail={"code": "PROFILE_INCOMPATIBLE"})
    body = body.model_copy(
        update={
            "settings": RuntimeSettings.model_validate(settings),
            "warm_for_seconds": None,
        }
    )
    return invoke(service.create_profile, db, body, user.id)


@router.get("/access/policies")
def policies(user=Depends(access_session), db: Session = Depends(get_db)):
    ready()
    return invoke(service.list_policies, db, user.id)


@router.post("/access/policies", status_code=201)
def policy_create(
    body: C.PolicyCreate, user=Depends(access_session), db: Session = Depends(get_db)
):
    return invoke(service.create_policy, db, body, user.id)


@router.post("/access/policies/{id}/revisions", status_code=201)
def policy_revise(
    id: str,
    body: C.PolicyUpdate,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    ready()
    return invoke(service.revise_policy, db, id, body, user.id)


@router.get("/access/roles")
def roles(user=Depends(access_session), db: Session = Depends(get_db)):
    ready()
    invoke(policy.authorize, db, user.id, "access.grants.manage")
    return {k: sorted(v) for k, v in policy.ROLES.items()}


@router.get("/access/subjects")
def subjects(user=Depends(access_session), db: Session = Depends(get_db)):
    # Subject directory is bootstrap-only. Delegated admins address subjects by explicit ID.
    ready()
    invoke(service.bootstrap, db, user.id)
    return [
        {"id": u.id, "username": u.username, "email": u.email}
        for u in db.query(User).filter_by(is_active=True)
    ]


# Deprecated aliases (spec 0018 §4.5, CA8): the engines family of
# /admin/iam/bindings, with the 0009 contract unchanged (tests/test_iam_access_grant_aliases.py).
@router.get("/access/grants", deprecated=True)
def grants(user=Depends(access_session), db: Session = Depends(get_db)):
    ready()
    return invoke(service.list_grants, db, user.id)


@router.post("/access/grants", status_code=201, deprecated=True)
def grant(
    body: C.GrantCreate, user=Depends(access_session), db: Session = Depends(get_db)
):
    return invoke(service.create_grant, db, body, user.id)


@router.post("/access/grants/{id}/revoke", deprecated=True)
def revoke(
    id: str,
    body: C.Version,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    ready()
    return invoke(service.revoke, db, id, body.version, user.id)


@router.get("/access/engine-attributes")
def attributes(user=Depends(access_session), db: Session = Depends(get_db)):
    ready()
    invoke(service.bootstrap, db, user.id)
    return [
        dict(engine_id=a.engine_id, environment=a.environment, version=a.version)
        for a in db.query(EngineAttributes)
    ]


@router.put("/access/engine-attributes/{id}")
def classify(
    id: str,
    body: C.AttributesUpdate,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    ready()
    invoke(service.bootstrap, db, user.id)
    e = scoped_engine(db, id, user.id)
    return invoke(service.set_attributes, db, e, body, user.id)


@router.get("/access/resources")
def resources(user=Depends(access_session), db: Session = Depends(get_db)):
    ready()
    invoke(service.bootstrap, db, user.id)
    rows = []
    for r in db.query(ControlResource):
        s = db.get(ResourceScope, r.key)
        rows.append(
            dict(
                key=r.key,
                owner_engine_id=r.owner_engine_id,
                version=s.version if s else 0,
                qualified=bool(s and s.qualified),
                consumers=s.consumers if s else [],
            )
        )
    return rows


@router.put("/access/resources")
def qualify(
    body: C.ScopeUpdate, user=Depends(access_session), db: Session = Depends(get_db)
):
    ready()
    return invoke(service.set_scope, db, body, user.id)


@router.get("/execution-profile-hosts")
def hosts(user=Depends(access_session), db: Session = Depends(get_db)):
    from shared.engine_control.models import ControlHost

    return policy.visible_catalog(
        db,
        user.id,
        [
            dict(id=h.id, seen_at=h.seen_at, services=h.inventory.get("services", []))
            for h in db.query(ControlHost)
        ],
        "host",
    )


@router.get("/access/installation-principals")
def principals(user=Depends(access_session), db: Session = Depends(get_db)):
    ready()
    invoke(service.bootstrap, db, user.id)
    from shared.access.models import ServicePrincipal

    return [
        dict(id=p.id, active=p.active, version=p.version, purpose=p.purpose)
        for p in db.query(ServicePrincipal)
    ]


@router.post("/access/installation-principals", status_code=201)
def principal_create(
    body: C.PrincipalCreate, user=Depends(access_session), db: Session = Depends(get_db)
):
    ready()
    authority = invoke(policy.epoch, db, True)
    invoke(service.bootstrap, db, user.id)
    from shared.access.models import ServicePrincipal

    if db.get(ServicePrincipal, body.id):
        raise HTTPException(409, detail={"code": "PRINCIPAL_EXISTS"})
    p = ServicePrincipal(id=body.id, purpose="installation_cli")
    db.add(p)
    authority.version += 1
    policy.audit(db, user.id, "access.principal_registered", body.id)
    db.commit()
    return dict(id=p.id, active=p.active, version=p.version, purpose=p.purpose)


@router.put("/access/installation-principals/{id}")
def principal_state(
    id: str,
    body: C.PrincipalState,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    ready()
    authority = invoke(policy.epoch, db, True)
    invoke(service.bootstrap, db, user.id)
    from shared.access.models import ServicePrincipal

    p = (
        db.query(ServicePrincipal)
        .filter_by(id=id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if not p:
        raise HTTPException(404, detail={"code": "PRINCIPAL_NOT_FOUND"})
    invoke(service._version, p, body.version)
    p.active = body.active
    p.version += 1
    authority.version += 1
    policy.audit(db, user.id, "access.principal_changed", id, {"active": p.active})
    db.commit()
    return dict(id=p.id, active=p.active, version=p.version, purpose=p.purpose)


@router.put("/access/subjects/{id}/state")
def subject_state(
    id: str,
    body: C.SubjectState,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    ready()
    authority = invoke(policy.epoch, db, True)
    invoke(service.bootstrap, db, user.id)
    target = (
        db.query(User).filter_by(id=id).populate_existing().with_for_update().first()
    )
    if not target:
        raise HTTPException(404, detail={"code": "SUBJECT_NOT_FOUND"})
    if (target.is_active, target.is_admin) != (
        body.expected_is_active,
        body.expected_is_admin,
    ):
        raise HTTPException(409, detail={"code": "VERSION_CONFLICT"})
    try:
        root.refuse_root_change(target, body)
    except root.RootError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code})
    target.is_active = body.is_active
    target.is_admin = body.is_admin
    authority.version += 1
    policy.audit(
        db,
        user.id,
        "access.subject_changed",
        id,
        {"is_active": target.is_active, "is_admin": target.is_admin},
    )
    db.commit()
    return dict(id=target.id, is_active=target.is_active, is_admin=target.is_admin)
