"""Library and grants, with one SQL ordering point for authorization changes."""

from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from shared.models import User, Engine
from shared.admin import is_effective_admin
from shared.engine_control import catalog, registry
from shared.engine_control.contracts import RuntimeSettings
from shared.engine_control import service as control
from shared.access import policy
from shared.access.models import (
    ExecutionProfile,
    ExecutionRevision,
    AccessPolicy,
    PolicyRevision,
    EngineAttributes,
    ResourceScope,
)


def require_enabled():
    if not policy.enabled():
        raise control.ControlError("ACCESS_NOT_ENABLED", 503)


def _version(row, version):
    if row.version != version:
        raise control.ControlError("VERSION_CONFLICT")


def bootstrap(db, actor):
    user = db.query(User).filter_by(id=str(actor)).populate_existing().first()
    if not user or not user.is_active or not is_effective_admin(user):
        raise control.ControlError("ACCESS_DENIED", 403)


def get_profile(db, id, actor, permission="execution_profiles.read", lock=False):
    q = db.query(ExecutionProfile).filter_by(id=id).populate_existing()
    p = q.with_for_update().first() if lock else q.first()
    if not p or not visible_profile(db, p, actor):
        raise control.ControlError("PROFILE_NOT_FOUND", 404)
    policy.authorize(db, actor, permission, profile=p)
    return p


def revision_view(r):
    return dict(
        id=r.id,
        revision=r.revision,
        settings=r.settings,
        warm_for_seconds=r.warm_for_seconds,
        model_fingerprint=r.model_fingerprint,
        content_hash=r.content_hash,
        published_at=r.published_at,
    )


def view(db, p, actor, details=False):
    out = dict(
        id=p.id,
        name=p.name,
        description=p.description,
        adapter_type=p.adapter_type,
        feature=p.feature,
        environment=p.environment,
        status=p.status,
        version=p.version,
        latest_published_revision_id=(
            p.latest_published_revision_id
            if not p.latest_published_revision_id
            or visible_revision(db, p, p.latest_published_revision_id, actor)
            else None
        ),
        permissions=[
            a
            for a in ("read", "update", "publish", "archive")
            if policy.allowed(db, actor, "execution_profiles." + a, profile=p)
        ],
    )
    if details:
        out["revisions"] = [
            revision_view(r)
            for r in db.query(ExecutionRevision)
            .filter_by(profile_id=p.id)
            .order_by(ExecutionRevision.revision.desc())
            if policy.allowed(
                db, actor, "execution_profiles.read", profile=p, runtime=r.settings
            )
        ]
        if p.latest_published_revision_id not in {r["id"] for r in out["revisions"]}:
            out["latest_published_revision_id"] = None
        from shared.engine_control.models import RuntimeProfile

        out["bindings"] = [
            dict(
                engine_id=r.engine_id,
                feature=r.feature,
                revision=r.revision,
                applied_at=r.applied_at,
            )
            for r in db.query(RuntimeProfile)
            .join(
                ExecutionRevision,
                RuntimeProfile.source_profile_revision_id == ExecutionRevision.id,
            )
            .filter(ExecutionRevision.profile_id == p.id)
            if policy.allowed(
                db,
                actor,
                "engines.read",
                engine=db.get(Engine, r.engine_id),
                profile=p,
                feature=r.feature,
                runtime=r.profile,
            )
        ]
    return out


def list_profiles(db, actor):
    return [
        view(db, p, actor)
        for p in policy.scoped_query(
            db, actor, db.query(ExecutionProfile), "profile"
        ).order_by(ExecutionProfile.created_at.desc())
        if visible_profile(db, p, actor)
    ]


def normalize(adapter, feature, body):
    settings = body.settings.model_dump(mode="json")
    if settings["warm_until"] is not None:
        raise control.ControlError("USE_WARM_DURATION", 422)
    d = registry.descriptor(adapter, settings["adapter_version"])
    if feature not in d["features"]:
        raise control.ControlError("FEATURE_NOT_SUPPORTED", 422)
    fields = {f["name"]: f for f in d["provider_fields"]}
    if set(settings["provider_settings"]) != set(fields):
        raise control.ControlError("PROVIDER_FIELDS_REQUIRED", 422)
    for k, v in settings["provider_settings"].items():
        f = fields[k]
        import re

        if f["type"] == "secret" or re.search(
            r"token|secret|password|credential|api_key|access_key", k, re.I
        ):
            raise control.ControlError("CREDENTIALS_NOT_ALLOWED_IN_PROFILE", 422)
        if f["type"] == "number":
            if (
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or v < f.get("min", v)
                or v > f.get("max", v)
            ):
                raise control.ControlError("INVALID_PROVIDER_VALUE", 422)
        elif not isinstance(v, str) or not v or len(v) > 256:
            raise control.ControlError("INVALID_PROVIDER_VALUE", 422)
        if f.get("options") and v not in {o["value"] for o in f["options"]}:
            raise control.ControlError("INVALID_PROVIDER_VALUE", 422)
    model = catalog.get(settings["model_profile_id"], adapter, feature)
    if (
        settings["min_ready_replicas"]
        and d.get("requires_budget")
        and not body.warm_for_seconds
    ):
        raise control.ControlError("WARM_DURATION_REQUIRED", 422)
    return settings, control.digest(model)


def add_revision(db, p, body, actor):
    settings, fingerprint = normalize(p.adapter_type, p.feature, body)
    policy.authorize(
        db,
        actor,
        "execution_profiles.create" if not p.id else "execution_profiles.update",
        profile=p,
        runtime=settings,
        warm_seconds=body.warm_for_seconds,
        creating=not p.id,
    )
    n = (
        db.query(func.max(ExecutionRevision.revision))
        .filter(ExecutionRevision.profile_id == p.id)
        .scalar()
        or 0
    ) + 1
    r = ExecutionRevision(
        profile_id=p.id,
        revision=n,
        settings=settings,
        warm_for_seconds=body.warm_for_seconds,
        model_fingerprint=fingerprint,
        content_hash=control.digest(
            dict(
                settings=settings,
                warm_for_seconds=body.warm_for_seconds,
                model_fingerprint=fingerprint,
            )
        ),
        created_by=actor,
    )
    db.add(r)
    db.flush()
    return r


def create_profile(db, body, actor):
    require_enabled()
    policy.epoch(db, True)
    p = ExecutionProfile(
        name=body.name.strip(),
        description=body.description,
        adapter_type=body.adapter_type,
        feature=body.feature,
        environment=body.environment,
        created_by=actor,
    )
    settings, _ = normalize(p.adapter_type, p.feature, body)
    decision = policy.authorize(
        db,
        actor,
        "execution_profiles.create",
        profile=p,
        runtime=settings,
        warm_seconds=body.warm_for_seconds,
        creating=True,
    )
    p.origin_grant_id = decision.get("grant_id")
    db.add(p)
    db.flush()
    # Creation was authorized before assigning an ID; do not require update of a new ID.
    settings, fingerprint = normalize(p.adapter_type, p.feature, body)
    r = ExecutionRevision(
        profile_id=p.id,
        revision=1,
        settings=settings,
        warm_for_seconds=body.warm_for_seconds,
        model_fingerprint=fingerprint,
        content_hash=control.digest(
            dict(
                settings=settings,
                warm_for_seconds=body.warm_for_seconds,
                model_fingerprint=fingerprint,
            )
        ),
        created_by=actor,
    )
    db.add(r)
    policy.audit(db, actor, "execution_profile.created", p.id)
    db.commit()
    return view(db, p, actor, True)


def revise(db, id, body, actor):
    require_enabled()
    policy.epoch(db, True)
    p = get_profile(db, id, actor, "execution_profiles.update", True)
    _version(p, body.version)
    if p.status == "archived":
        raise control.ControlError("PROFILE_ARCHIVED")
    add_revision(db, p, body, actor)
    p.version += 1
    policy.audit(db, actor, "execution_profile.revised", p.id)
    db.commit()
    return view(db, p, actor, True)


def metadata(db, id, body, actor):
    policy.epoch(db, True)
    p = get_profile(db, id, actor, "execution_profiles.update", True)
    _version(p, body.version)
    p.name = body.name.strip()
    p.description = body.description
    p.version += 1
    policy.audit(db, actor, "execution_profile.metadata", id)
    db.commit()
    return view(db, p, actor, True)


def publish(db, id, body, actor):
    policy.epoch(db, True)
    p = get_profile(db, id, actor, "execution_profiles.publish", True)
    _version(p, body.version)
    r = db.get(ExecutionRevision, body.revision_id)
    if not r or r.profile_id != p.id:
        raise control.ControlError("REVISION_NOT_FOUND", 404)
    if p.status == "archived" or r.published_at:
        raise control.ControlError("REVISION_NOT_PUBLISHABLE")
    current = catalog.get(r.settings["model_profile_id"], p.adapter_type, p.feature)
    if control.digest(current) != r.model_fingerprint:
        raise control.ControlError("MODEL_METADATA_CHANGED")
    policy.authorize(
        db,
        actor,
        "execution_profiles.publish",
        profile=p,
        runtime=r.settings,
        warm_seconds=r.warm_for_seconds,
    )
    r.published_at = datetime.utcnow()
    p.latest_published_revision_id = r.id
    p.status = "published"
    p.version += 1
    policy.audit(db, actor, "execution_profile.published", id, {"revision_id": r.id})
    db.commit()
    return view(db, p, actor, True)


def archive(db, id, version, actor):
    policy.epoch(db, True)
    p = get_profile(db, id, actor, "execution_profiles.archive", True)
    _version(p, version)
    p.status = "archived"
    p.version += 1
    policy.audit(db, actor, "execution_profile.archived", id)
    db.commit()
    return view(db, p, actor, True)


def bind(db, engine, body, actor):
    require_enabled()
    policy.epoch(db, True)
    engine = control.locked_engine(db, engine.id)
    _version(engine, body.version)
    r = db.get(ExecutionRevision, body.revision_id)
    if not r:
        raise control.ControlError("REVISION_NOT_FOUND", 404)
    p = get_profile(db, r.profile_id, actor)
    if p.status == "archived" or not r.published_at:
        raise control.ControlError("PUBLISHED_REVISION_REQUIRED", 422)
    if p.adapter_type != engine.adapter_type or p.feature != body.feature:
        raise control.ControlError("PROFILE_INCOMPATIBLE", 422)
    attr = db.get(EngineAttributes, engine.id)
    if not attr or attr.environment != p.environment:
        raise control.ControlError("ENGINE_ENVIRONMENT_REQUIRED", 422)
    model = catalog.get(r.settings["model_profile_id"], p.adapter_type, p.feature)
    if control.digest(model) != r.model_fingerprint:
        raise control.ControlError("MODEL_METADATA_CHANGED")
    settings = RuntimeSettings.model_validate(r.settings).model_dump(mode="json")
    if r.warm_for_seconds:
        settings["warm_until"] = (
            datetime.now(timezone.utc) + timedelta(seconds=r.warm_for_seconds)
        ).isoformat()
    return control.save_profile(
        db,
        engine,
        body.feature,
        settings,
        body.version,
        actor,
        source_profile_revision_id=r.id,
        source_hash=r.content_hash,
    )


def _delegator(db, actor, permission_set, constraints, expires_at, delegation=None):
    user = db.get(User, actor)
    if is_effective_admin(user):
        return None
    for g in policy.grants(db, actor):
        envelope = g.delegation
        if "access.grants.manage" not in g.permissions or not envelope:
            continue
        if not set(permission_set).issubset(envelope["permissions"]):
            continue
        if not policy.subset(constraints, envelope["constraints"]):
            continue
        if expires_at > min(
            g.expires_at,
            datetime.utcnow() + timedelta(seconds=envelope["max_grant_seconds"]),
        ):
            continue
        if delegation and (
            not set(delegation["permissions"]).issubset(envelope["permissions"])
            or not policy.subset(delegation["constraints"], envelope["constraints"])
            or delegation["max_grant_seconds"] > envelope["max_grant_seconds"]
        ):
            continue
        return g.id
    raise control.ControlError("DELEGATION_EXCEEDED", 403)


def create_policy(db, body, actor):
    require_enabled()
    policy.epoch(db, True)
    policy.authorize(db, actor, "access.grants.manage")
    c = body.constraints.model_dump(mode="json")
    _delegator(db, actor, [], c, datetime.utcnow() + timedelta(seconds=60))
    p = AccessPolicy(name=body.name, created_by=actor)
    db.add(p)
    db.flush()
    r = PolicyRevision(policy_id=p.id, revision=1, constraints=c)
    db.add(r)
    db.flush()
    policy.audit(db, actor, "access.policy_created", p.id)
    db.commit()
    return policy_view(db, p)


def policy_view(db, p):
    return dict(
        id=p.id,
        name=p.name,
        version=p.version,
        revisions=[
            dict(id=r.id, revision=r.revision, constraints=r.constraints)
            for r in db.query(PolicyRevision)
            .filter_by(policy_id=p.id)
            .order_by(PolicyRevision.revision.desc())
        ],
    )


def list_policies(db, actor):
    policy.authorize(db, actor, "access.grants.manage")
    rows = []
    for p in db.query(AccessPolicy):
        v = policy_view(db, p)
        visible = []
        for r in v["revisions"]:
            try:
                _delegator(
                    db,
                    actor,
                    [],
                    r["constraints"],
                    datetime.utcnow() + timedelta(seconds=60),
                )
                visible.append(r)
            except control.ControlError:
                pass
        if visible:
            v["revisions"] = visible
            rows.append(v)
    return rows


def revise_policy(db, id, body, actor):
    policy.epoch(db, True)
    policy.authorize(db, actor, "access.grants.manage")
    p = db.query(AccessPolicy).filter_by(id=id).with_for_update().first()
    if not p:
        raise control.ControlError("POLICY_NOT_FOUND", 404)
    if id not in {v["id"] for v in list_policies(db, actor)}:
        raise control.ControlError("POLICY_NOT_FOUND", 404)
    c = body.constraints.model_dump(mode="json")
    _delegator(db, actor, [], c, datetime.utcnow() + timedelta(seconds=60))
    _version(p, body.version)
    p.version += 1
    r = PolicyRevision(policy_id=p.id, revision=p.version + 1, constraints=c)
    db.add(r)
    policy.audit(db, actor, "access.policy_revised", id)
    db.commit()
    return next(v for v in list_policies(db, actor) if v["id"] == p.id)


def grant_view(g):
    return dict(
        id=g.id,
        user_id=g.user_id,
        role=g.role,
        permissions=g.permissions,
        policy_revision_id=g.policy_revision_id,
        expires_at=g.expires_at,
        revoked_at=g.revoked_at,
        version=g.version,
        parent_id=g.parent_id,
        delegation=g.delegation,
    )


def create_grant(db, body, actor):
    """`POST /admin/access/grants`: an engines binding (spec 0018 §4.3)."""
    from shared.iam import bindings
    from shared.iam.engine_bindings import as_grant

    b = bindings.grant_engine(
        db,
        actor,
        subject_id=body.user_id,
        role=body.role,
        permissions=body.permissions,
        condition_ref=body.policy_revision_id,
        expires_at=body.expires_at,
        delegation=body.delegation,
    )
    return grant_view(as_grant(b))


def list_grants(db, actor):
    from shared.iam import bindings

    return [grant_view(g) for g in bindings.list_engine_grants(db, actor)]


def revoke(db, id, version, actor):
    from shared.iam import bindings
    from shared.iam.engine_bindings import as_grant

    return grant_view(as_grant(bindings.revoke_engine(db, actor, id, version)))


def set_attributes(db, engine, body, actor):
    authority = policy.epoch(db, True)
    bootstrap(db, actor)
    row = db.get(EngineAttributes, engine.id)
    if row is None:
        row = EngineAttributes(
            engine_id=engine.id, environment=body.environment, version=0
        )
        db.add(row)
    _version(row, body.version)
    row.environment = body.environment
    row.version += 1
    authority.version += 1
    policy.audit(
        db,
        actor,
        "access.engine_classified",
        engine.id,
        {"environment": body.environment},
    )
    db.commit()
    return dict(engine_id=engine.id, environment=row.environment, version=row.version)


def set_scope(db, body, actor):
    authority = policy.epoch(db, True)
    bootstrap(db, actor)
    from shared.engine_control.models import ControlResource

    if not db.get(ControlResource, body.key):
        raise control.ControlError("RESOURCE_NOT_FOUND", 404)
    for c in body.consumers:
        e = db.get(Engine, c.engine_id)
        if (
            not e
            or c.feature not in registry.descriptor(e.adapter_type)["features"]
            or not db.get(EngineAttributes, e.id)
        ):
            raise control.ControlError("CONSUMER_NOT_CLASSIFIED", 422)
    row = db.get(ResourceScope, body.key)
    if row is None:
        row = ResourceScope(key=body.key, version=0, consumers=[], qualified=False)
        db.add(row)
    _version(row, body.version)
    row.consumers = [c.model_dump() for c in body.consumers]
    row.qualified = body.qualified
    row.version += 1
    authority.version += 1
    policy.audit(
        db,
        actor,
        "access.resource_qualified",
        body.key,
        {"qualified": body.qualified, "consumers": row.consumers},
    )
    db.commit()
    return dict(
        key=row.key,
        consumers=row.consumers,
        qualified=row.qualified,
        version=row.version,
    )


def visible_profile(db, p, actor):
    if not policy.allowed(db, actor, "execution_profiles.read", profile=p):
        return False
    return any(
        policy.allowed(
            db, actor, "execution_profiles.read", profile=p, runtime=r.settings
        )
        for r in db.query(ExecutionRevision).filter_by(profile_id=p.id)
    )


def visible_revision(db, p, revision_id, actor):
    r = db.get(ExecutionRevision, revision_id)
    return bool(
        r
        and policy.allowed(
            db, actor, "execution_profiles.read", profile=p, runtime=r.settings
        )
    )
