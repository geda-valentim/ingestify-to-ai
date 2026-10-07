"""Functional contracts for the profile library and delegated engine control.

The adapter is deliberately a third provider: these tests never call Docker,
Modal or a paid service, and exercise the existing runtime/plan/outbox path.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.database import Base, get_db
from shared.config import get_settings
from shared.auth import get_current_active_user
from shared.models import User, Engine, AdminAudit
from shared.access import contracts as C, policy, service
from shared.access.models import (
    AuthorizationEpoch,
    EngineAttributes,
    ExecutionRevision,
    PolicyRevision,
    ResourceScope,
    EffectAdmission,
)
from shared.iam.models import IamBinding
from shared.engine_control import registry, service as control
from shared.engine_control.contracts import PlanRequest, utc_deadline
from shared.engine_control.models import (
    RuntimeProfile,
    EngineOperation,
    ControlResource,
    OperationOutbox,
)

ADAPTER = "profile-test-provider"
RESOURCE = "profile-test:account:shared-worker"


class Provider:
    def validate(self, engine, feature, settings, db):
        return {**settings, "model": "resolved-model", "service": "shared-worker"}

    def resource_keys(self, engine, feature, settings):
        return [RESOURCE]

    def plan(self, engine, request, settings, db):
        return {
            "stages": ["scaling"],
            "destructive": True,
            "drain": False,
            "estimated_max_usd": "0.10",
        }


def settings(**updates):
    raw = dict(
        binding={"workers": 2, "executions_per_worker": 1, "cpu": 1},
        model_profile_id="approved-profile-test",
        desired_replicas=1,
        max_replicas=2,
        memory_mb=512,
        min_ready_replicas=0,
        warmup_mode="manual",
        provider_settings={"zone": "test-a"},
    )
    raw.update(updates)
    return raw


def constraints(**updates):
    raw = dict(
        engine_ids=["engine-a"],
        adapters=[ADAPTER],
        features=["transcription"],
        environments=["development"],
        max_replicas=2,
        max_cpu=2,
        max_memory_mb=1024,
        max_concurrency=2,
        max_warm_seconds=3600,
        max_usd="0.20",
        model_ids=["approved-profile-test"],
    )
    raw.update(updates)
    return C.Constraints(**raw)


@pytest.fixture
def world(monkeypatch):
    sql = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(sql)
    factory = sessionmaker(bind=sql)
    monkeypatch.setattr(get_settings(), "engine_access_enabled", True)
    monkeypatch.setattr(get_settings(), "engine_control_enabled", True)
    monkeypatch.setattr(get_settings(), "admin_user_ids", "")
    descriptor = dict(
        type=ADAPTER,
        actions=["scale", "drain_stop"],
        features=["transcription", "document_conversion"],
        execution_mode="remote_runner",
        credential_fields=[],
        fields=[],
        provider_fields=[dict(name="zone", type="text")],
        model_profiles=[
            dict(
                id="approved-profile-test",
                title="Approved model",
                feature="transcription",
                adapters=[ADAPTER],
                approved=True,
                model="immutable-model",
                footprint_gb=1,
            )
        ],
    )
    registry.register(ADAPTER, descriptor, Provider)
    with factory() as db:
        for uid in [
            "bootstrap",
            "editor",
            "operator",
            "delegate",
            "observer",
            "outsider",
        ]:
            db.add(
                User(
                    id=uid,
                    username=uid,
                    email=uid + "@example.test",
                    hashed_password="unused",
                    is_admin=uid == "bootstrap",
                    is_active=True,
                )
            )
        for uid in ["engine-a", "engine-b"]:
            db.add(
                Engine(
                    id=uid,
                    slug=uid,
                    display_name=uid,
                    adapter_type=ADAPTER,
                    config={"features": {}},
                    deployments={},
                    version=0,
                    limit_usd=10,
                    min_remaining_usd=0,
                )
            )
            db.add(EngineAttributes(engine_id=uid, environment="development"))
        db.add(AuthorizationEpoch(id=1, version=0))
        db.add(ControlResource(key=RESOURCE, owner_engine_id="engine-a"))
        db.add(
            ResourceScope(
                key=RESOURCE,
                consumers=[dict(engine_id="engine-a", feature="transcription")],
                qualified=True,
            )
        )
        db.commit()
    yield factory
    registry._registry.pop((ADAPTER, 1), None)
    sql.dispose()


def grant_row(db, id):
    """The stored grant row: an engines `iam_binding` since spec 0018."""
    return db.get(IamBinding, id)


def grant_rows(db, user_id):
    """The stored grant rows of a user: engines `iam_bindings` since spec 0018."""
    return db.query(IamBinding).filter_by(subject_type="user", subject_id=user_id)


def grant(
    db,
    actor="operator",
    role="engine_operator",
    scope=None,
    permissions=None,
    creator="bootstrap",
    delegation=None,
    expires=None,
):
    p = service.create_policy(
        db,
        C.PolicyCreate(name="Test policy", constraints=scope or constraints()),
        "bootstrap",
    )
    return service.create_grant(
        db,
        C.GrantCreate(
            user_id=actor,
            role=role,
            permissions=permissions,
            policy_revision_id=p["revisions"][0]["id"],
            expires_at=expires or datetime.now(timezone.utc) + timedelta(minutes=30),
            delegation=delegation,
        ),
        creator,
    )


def draft(db, actor="bootstrap", **updates):
    raw = dict(
        name="CPU transcription",
        adapter_type=ADAPTER,
        feature="transcription",
        settings=settings(),
        environment="development",
    )
    raw.update(updates)
    return service.create_profile(db, C.ProfileCreate(**raw), actor)


def published(db, **updates):
    p = draft(db, **updates)
    return service.publish(
        db,
        p["id"],
        C.Publish(version=p["version"], revision_id=p["revisions"][0]["id"]),
        "bootstrap",
    )


def prepared(db, actor="operator"):
    p = published(db)
    service.bind(
        db,
        db.get(Engine, "engine-a"),
        C.Bind(
            version=0,
            feature="transcription",
            revision_id=p["latest_published_revision_id"],
        ),
        "bootstrap",
    )
    g = grant(db, actor=actor)
    plan = control.create_plan(
        db,
        db.get(Engine, "engine-a"),
        PlanRequest(type="scale", engine_version=1, max_usd="0.10"),
        actor,
    )
    return g, plan


def test_published_revision_is_explicit_and_draft_does_not_become_attachable(world):
    with world() as db:
        p = published(db)
        first = p["latest_published_revision_id"]
        original = deepcopy(db.get(ExecutionRevision, first).settings)
        p = service.revise(
            db,
            p["id"],
            C.RevisionCreate(
                version=p["version"], settings=settings(desired_replicas=2)
            ),
            "bootstrap",
        )
        assert p["latest_published_revision_id"] == first
        with pytest.raises(control.ControlError, match="PUBLISHED_REVISION_REQUIRED"):
            service.bind(
                db,
                db.get(Engine, "engine-a"),
                C.Bind(
                    version=0,
                    feature="transcription",
                    revision_id=p["revisions"][0]["id"],
                ),
                "bootstrap",
            )
        db.rollback()
        result = service.bind(
            db,
            db.get(Engine, "engine-a"),
            C.Bind(version=0, feature="transcription", revision_id=first),
            "bootstrap",
        )
        assert result["source_profile_revision_id"] == first
        assert db.get(ExecutionRevision, first).settings == original
        assert db.get(Engine, "engine-a").config["features"] == {}
        assert db.query(OperationOutbox).count() == 0
        assert db.query(RuntimeProfile).one().applied_at is None


def test_binding_freezes_source_hash_warm_deadline_and_rejects_retry(world):
    with world() as db:
        p = published(db, warm_for_seconds=120)
        r = db.get(ExecutionRevision, p["latest_published_revision_id"])
        before = datetime.utcnow()
        result = service.bind(
            db,
            db.get(Engine, "engine-a"),
            C.Bind(version=0, feature="transcription", revision_id=r.id),
            "bootstrap",
        )
        deadline = utc_deadline(result["profile"]["warm_until"])
        assert 119 <= (deadline - before).total_seconds() <= 121
        assert result["source_hash"] == r.content_hash
        assert r.settings["warm_until"] is None
        with pytest.raises(control.ControlError, match="VERSION_CONFLICT"):
            service.bind(
                db,
                db.get(Engine, "engine-a"),
                C.Bind(version=0, feature="transcription", revision_id=r.id),
                "bootstrap",
            )
        db.rollback()
        assert db.query(RuntimeProfile).count() == 1
        assert (
            utc_deadline(db.query(RuntimeProfile).one().profile["warm_until"])
            == deadline
        )


@pytest.mark.parametrize("at_publish", [True, False])
def test_model_catalog_drift_is_rejected(world, at_publish):
    with world() as db:
        p = draft(db) if at_publish else published(db)
        registry.descriptor(ADAPTER)["model_profiles"][0][
            "model"
        ] = "changed-after-approval"
        with pytest.raises(control.ControlError, match="MODEL_METADATA_CHANGED"):
            if at_publish:
                service.publish(
                    db,
                    p["id"],
                    C.Publish(
                        version=p["version"], revision_id=p["revisions"][0]["id"]
                    ),
                    "bootstrap",
                )
            else:
                service.bind(
                    db,
                    db.get(Engine, "engine-a"),
                    C.Bind(
                        version=0,
                        feature="transcription",
                        revision_id=p["latest_published_revision_id"],
                    ),
                    "bootstrap",
                )
        db.rollback()
        assert db.query(RuntimeProfile).count() == 0


def test_templates_reject_absolute_warm_deadline_and_arbitrary_provider_fields(world):
    with world() as db:
        with pytest.raises(control.ControlError, match="USE_WARM_DURATION"):
            draft(db, settings=settings(warm_until=datetime.now(timezone.utc)))
        db.rollback()
        with pytest.raises(control.ControlError, match="PROVIDER_FIELDS_REQUIRED"):
            draft(
                db,
                settings=settings(
                    provider_settings={"zone": "test-a", "token": "not-allowed"}
                ),
            )
        db.rollback()
        assert db.query(ExecutionRevision).count() == 0


def test_archive_preserves_history_and_prevents_future_bindings(world):
    with world() as db:
        p = published(db)
        r = p["latest_published_revision_id"]
        service.bind(
            db,
            db.get(Engine, "engine-a"),
            C.Bind(version=0, feature="transcription", revision_id=r),
            "bootstrap",
        )
        service.archive(db, p["id"], p["version"], "bootstrap")
        with pytest.raises(control.ControlError, match="PUBLISHED_REVISION_REQUIRED"):
            service.bind(
                db,
                db.get(Engine, "engine-a"),
                C.Bind(version=1, feature="transcription", revision_id=r),
                "bootstrap",
            )
        db.rollback()
        assert db.get(ExecutionRevision, r).published_at is not None
        assert db.query(RuntimeProfile).count() == 1


def test_creation_uses_attributes_but_author_does_not_gain_cross_environment_access(
    world,
):
    with world() as db:
        grant(db, actor="editor", role="profile_editor")
        p = draft(db, actor="editor")
        assert p["permissions"] == ["read", "update", "publish", "archive"]
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            draft(db, actor="editor", environment="production")
        db.rollback()
        assert len(service.list_profiles(db, "editor")) == 1
        assert service.list_profiles(db, "outsider") == []


def test_profile_id_allowlist_cannot_create_an_unlisted_profile(world):
    with world() as db:
        grant(
            db,
            actor="editor",
            role="profile_editor",
            scope=constraints(profile_ids=["fixed-profile"]),
        )
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            draft(db, actor="editor")


def test_policy_revision_is_pinned_and_new_revision_does_not_widen_old_grant(world):
    with world() as db:
        g = grant(db, actor="observer", role="observer")
        old = db.get(PolicyRevision, g["policy_revision_id"])
        new = service.revise_policy(
            db,
            old.policy_id,
            C.PolicyUpdate(
                version=0, constraints=constraints(engine_ids=["engine-a", "engine-b"])
            ),
            "bootstrap",
        )
        assert new["revisions"][0]["id"] != old.id
        assert policy.allowed(
            db, "observer", "engines.read", engine=db.get(Engine, "engine-a")
        )
        assert not policy.allowed(
            db, "observer", "engines.read", engine=db.get(Engine, "engine-b")
        )


def test_whole_grant_must_authorize_combined_permission_and_scope(world):
    with world() as db:
        grant(db, permissions=["engine_operations.plan"])
        grant(db, permissions=["engine_operations.execute.scale"])
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            policy.authorize(
                db,
                "operator",
                {"engine_operations.plan", "engine_operations.execute.scale"},
                engine=db.get(Engine, "engine-a"),
                feature="transcription",
            )


@pytest.mark.parametrize(
    "change", ["unqualified", "unknown-consumer", "other-engine", "other-feature"]
)
def test_resource_authority_covers_every_consumer_not_only_owner(world, change):
    with world() as db:
        grant(db)
        scope = db.get(ResourceScope, RESOURCE)
        if change == "unqualified":
            scope.qualified = False
        else:
            consumer = {"engine_id": "engine-a", "feature": "transcription"}
            if change == "unknown-consumer":
                consumer["engine_id"] = "not-registered"
            if change == "other-engine":
                consumer["engine_id"] = "engine-b"
            if change == "other-feature":
                consumer["feature"] = "document_conversion"
            scope.consumers = scope.consumers + [consumer]
        db.commit()
        assert db.get(ControlResource, RESOURCE).owner_engine_id == "engine-a"
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            policy.authorize(
                db,
                "operator",
                "engine_operations.execute.scale",
                engine=db.get(Engine, "engine-a"),
                feature="transcription",
                resources=[RESOURCE],
            )


def test_read_scope_is_independent_of_execution_cost_limits(world):
    with world() as db:
        grant(
            db,
            actor="observer",
            role="observer",
            scope=constraints(max_replicas=0, max_usd="0"),
        )
        p = published(db)
        assert service.get_profile(db, p["id"], "observer").id == p["id"]
        assert policy.allowed(
            db,
            "observer",
            "engines.read",
            engine=db.get(Engine, "engine-a"),
            resources=[RESOURCE],
        )
        assert not policy.allowed(
            db,
            "observer",
            "engine_operations.execute.scale",
            engine=db.get(Engine, "engine-a"),
        )


@pytest.mark.parametrize(
    "runtime",
    [
        settings(max_replicas=3, binding={"workers": 3, "cpu": 1}),
        settings(memory_mb=2048),
        settings(binding={"workers": 2, "cpu": 3}),
        settings(binding={"workers": 2}),
        settings(memory_mb=None),
    ],
)
def test_execution_envelope_rejects_excess_or_unspecified_provider_defaults(
    world, runtime
):
    with world() as db:
        grant(db)
        assert not policy.allowed(
            db,
            "operator",
            "engine_operations.execute.scale",
            engine=db.get(Engine, "engine-a"),
            feature="transcription",
            runtime=runtime,
        )


def test_revocation_blocks_enqueue_and_idempotent_replay(world):
    with world() as db:
        g, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        service.revoke(db, g["id"], 0, "bootstrap")
        for key in ["once", "new-request"]:
            with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
                control.enqueue(db, p["plan_id"], p["plan_hash"], key, "operator", True)
            db.rollback()
        assert db.query(EngineOperation).count() == 1
        assert db.query(OperationOutbox).count() == 1
        assert db.get(EngineOperation, op["operation_id"]).actor_id == "operator"


def test_revocation_before_effect_blocks_admission_and_prior_admission_stays_uncertain(
    world,
):
    with world() as db:
        g, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        gen = control.claim(db, op["operation_id"], "test-executor")
        control.admit_effect(db, op["operation_id"], gen, "sdk:first")
        db.commit()
        admission = db.query(EffectAdmission).one()
        before = admission.epoch
        service.revoke(db, g["id"], 0, "bootstrap")
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            control.admit_effect(db, op["operation_id"], gen, "sdk:second")
        db.rollback()
        assert db.query(EffectAdmission).count() == 1
        assert admission.state == "uncertain"
        assert admission.epoch == before < db.get(AuthorizationEpoch, 1).version


def test_duplicate_effect_admission_cannot_replay_the_sdk_step(world):
    with world() as db:
        _, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        gen = control.claim(db, op["operation_id"], "executor")
        control.admit_effect(db, op["operation_id"], gen, "sdk:scale")
        db.commit()
        with pytest.raises(control.ControlError, match="EFFECT_ALREADY_ADMITTED"):
            control.admit_effect(db, op["operation_id"], gen, "sdk:scale")
        db.rollback()
        assert db.query(EffectAdmission).count() == 1


def test_delegation_envelope_does_not_grant_execution_and_parent_revoke_invalidates_child(
    world,
):
    with world() as db:
        envelope = C.Delegation(
            permissions=sorted(policy.ROLES["observer"]),
            constraints=constraints(),
            max_grant_seconds=1800,
        )
        parent = grant(db, actor="delegate", role="access_admin", delegation=envelope)
        assert not policy.allowed(
            db, "delegate", "engines.read", engine=db.get(Engine, "engine-a")
        )
        child = grant(
            db,
            actor="observer",
            role="observer",
            creator="delegate",
            expires=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        assert child["parent_id"] == parent["id"]
        assert policy.allowed(
            db, "observer", "engines.read", engine=db.get(Engine, "engine-a")
        )
        service.revoke(db, parent["id"], 0, "bootstrap")
        assert not policy.allowed(
            db, "observer", "engines.read", engine=db.get(Engine, "engine-a")
        )


def test_delegate_cannot_expand_scopes_or_permissions(world):
    with world() as db:
        envelope = C.Delegation(
            permissions=sorted(policy.ROLES["observer"]),
            constraints=constraints(),
            max_grant_seconds=1800,
        )
        grant(db, actor="delegate", role="access_admin", delegation=envelope)
        with pytest.raises(control.ControlError, match="DELEGATION_EXCEEDED"):
            service.create_policy(
                db,
                C.PolicyCreate(
                    name="Expanded",
                    constraints=constraints(engine_ids=["engine-a", "engine-b"]),
                ),
                "delegate",
            )
        db.rollback()
        with pytest.raises(control.ControlError, match="DELEGATION_EXCEEDED"):
            grant(
                db,
                creator="delegate",
                expires=datetime.now(timezone.utc) + timedelta(minutes=10),
            )


@pytest.mark.parametrize("change", ["inactive", "expired", "revoked"])
def test_stale_session_identity_cannot_override_current_sql_authority(world, change):
    with world() as db:
        g = grant(db, actor="observer", role="observer")
        if change == "inactive":
            db.get(User, "observer").is_active = False
        elif change == "expired":
            grant_row(db, g["id"]).expires_at = datetime.utcnow() - timedelta(
                seconds=1
            )
        else:
            grant_row(db, g["id"]).revoked_at = datetime.utcnow()
        db.commit()
        assert not policy.allowed(
            db, "observer", "engines.read", engine=db.get(Engine, "engine-a")
        )


def test_cancel_and_recovery_record_current_actor_without_replacing_initiator(world):
    with world() as db:
        g, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        control.request_cancel(db, op["operation_id"], "bootstrap")
        row = db.get(EngineOperation, op["operation_id"])
        assert row.actor_id == "operator"
        assert row.cancel_requested_by == "bootstrap"
        row.state = "needs_attention"
        row.handles = {"executor_exited": True}
        db.commit()
        service.revoke(db, g["id"], 0, "bootstrap")
        control.request_recovery(db, row.id, "bootstrap")
        assert row.actor_id == "operator" and row.recovery_requested_by == "bootstrap"
        assert policy.operation_authority(db, row)["bootstrap"]
        assert (
            db.query(AdminAudit)
            .filter_by(action="engine.recovery_requested", actor_user_id="bootstrap")
            .count()
            == 1
        )


@pytest.fixture
def client(world):
    from api.access_routes import router as access_router
    from api.engine_control_routes import router as control_router

    app = FastAPI()
    app.include_router(access_router)
    app.include_router(control_router)
    actor = {"id": "bootstrap"}

    def db_override():
        with world() as db:
            yield db

    def user_override():
        with world() as db:
            return db.get(User, actor["id"])

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_active_user] = user_override
    with TestClient(app) as http:
        yield http, actor


HEADERS = {"Authorization": "Bearer overridden-test-session"}


def test_api_library_is_jwt_only_and_flag_is_explicit(world, client, monkeypatch):
    http, _ = client
    assert http.get("/admin/execution-profiles").status_code == 403
    assert (
        http.get(
            "/admin/execution-profiles", headers={**HEADERS, "X-API-Key": "ignored"}
        ).status_code
        == 403
    )
    monkeypatch.setattr(get_settings(), "engine_access_enabled", False)
    response = http.get("/admin/execution-profiles", headers=HEADERS)
    assert (
        response.status_code == 503
        and response.json()["detail"]["code"] == "ACCESS_NOT_ENABLED"
    )


def test_api_observer_cannot_mutate_or_fetch_foreign_engine(world, client):
    http, actor = client
    with world() as db:
        grant(db, actor="observer", role="observer")
        p = published(db)
    actor["id"] = "observer"
    assert (
        http.get("/admin/engines/engine-a/capabilities", headers=HEADERS).status_code
        == 200
    )
    assert (
        http.get("/admin/engines/engine-b/capabilities", headers=HEADERS).status_code
        == 404
    )
    assert (
        http.get("/admin/execution-profiles", headers=HEADERS).json()[0]["id"]
        == p["id"]
    )
    response = http.post(
        "/admin/execution-profiles/" + p["id"] + "/publish",
        headers=HEADERS,
        json={
            "version": p["version"],
            "revision_id": p["latest_published_revision_id"],
        },
    )
    assert response.status_code == 403
    assert http.get("/admin/access/subjects", headers=HEADERS).status_code == 403


def test_api_configurator_binds_published_revision_but_raw_put_is_bootstrap_only(
    world, client
):
    http, actor = client
    with world() as db:
        grant(db, actor="operator", role="runtime_configurator")
        p = published(db)
    actor["id"] = "operator"
    path = "/admin/engines/engine-a/runtime-profile"
    assert (
        http.put(
            path,
            headers=HEADERS,
            json={"version": 0, "feature": "transcription", "profile": settings()},
        ).status_code
        == 403
    )
    response = http.post(
        path + "/bind",
        headers=HEADERS,
        json={
            "version": 0,
            "feature": "transcription",
            "revision_id": p["latest_published_revision_id"],
        },
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["source_profile_revision_id"]
        == p["latest_published_revision_id"]
    )


def test_api_operation_detail_events_and_cursor_are_hidden_after_revocation(
    world, client
):
    http, actor = client
    with world() as db:
        g, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        grant(db, actor="observer", role="observer")
    actor["id"] = "observer"
    base = "/admin/engine-operations/" + op["operation_id"]
    assert http.get(base, headers=HEADERS).status_code == 200
    with world() as db:
        observer_grant = grant_rows(db, "observer").one()
        service.revoke(db, observer_grant.id, 0, "bootstrap")
        # Retain unrelated navigation permission so denial occurs at the resource boundary.
        grant(
            db,
            actor="observer",
            role="observer",
            scope=constraints(engine_ids=["engine-b"]),
        )
    for suffix in ["", "/events?after=1"]:
        assert http.get(base + suffix, headers=HEADERS).status_code == 404


def test_legacy_import_whitelists_resolved_fields_and_preserves_applied_history(
    world, client
):
    http, _ = client
    with world() as db:
        control.save_profile(
            db, db.get(Engine, "engine-a"), "transcription", settings(), 0, "bootstrap"
        )
        legacy = db.query(RuntimeProfile).one()
        original = deepcopy(legacy.profile)
        legacy.applied_at = datetime.utcnow()
        db.commit()
    body = dict(
        name="Imported",
        adapter_type=ADAPTER,
        feature="transcription",
        environment="development",
        settings=settings(),
    )
    response = http.post(
        "/admin/engines/engine-a/runtime-profile/import", headers=HEADERS, json=body
    )
    assert response.status_code == 201, response.text
    revision = response.json()["revisions"][0]
    assert revision["published_at"] is None
    assert not {"model", "service"} & set(revision["settings"])
    with world() as db:
        assert db.query(RuntimeProfile).one().profile == original
        assert db.query(RuntimeProfile).one().applied_at is not None


def test_bind_cannot_combine_read_grant_with_different_profile_configurator_scope(
    world,
):
    with world() as db:
        permitted = published(db, name="Permitted")
        foreign = published(db, name="Read only")
        grant(
            db,
            role="runtime_configurator",
            scope=constraints(profile_ids=[permitted["id"]]),
        )
        grant(db, role="observer", scope=constraints(profile_ids=[foreign["id"]]))
        assert service.get_profile(db, foreign["id"], "operator")
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            service.bind(
                db,
                db.get(Engine, "engine-a"),
                C.Bind(
                    version=0,
                    feature="transcription",
                    revision_id=foreign["latest_published_revision_id"],
                ),
                "operator",
            )
        db.rollback()
        assert db.query(RuntimeProfile).count() == 0


def test_plan_respects_source_profile_id_allowlist(world):
    with world() as db:
        permitted = published(db, name="Permitted")
        foreign = published(db, name="Other library profile")
        service.bind(
            db,
            db.get(Engine, "engine-a"),
            C.Bind(
                version=0,
                feature="transcription",
                revision_id=foreign["latest_published_revision_id"],
            ),
            "bootstrap",
        )
        grant(db, scope=constraints(profile_ids=[permitted["id"]]))
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            control.create_plan(
                db,
                db.get(Engine, "engine-a"),
                PlanRequest(type="scale", engine_version=1, max_usd="0.10"),
                "operator",
            )


def test_rebinding_checks_old_applied_and_new_desired_resource_consumers(
    world, monkeypatch
):
    other = "profile-test:account:old-applied-worker"
    monkeypatch.setattr(
        Provider,
        "resource_keys",
        lambda self, e, f, p: [
            other if p["provider_settings"]["zone"] == "test-b" else RESOURCE
        ],
    )
    with world() as db:
        db.add(ControlResource(key=other, owner_engine_id="engine-a"))
        db.add(
            ResourceScope(
                key=other,
                consumers=[dict(engine_id="engine-b", feature="transcription")],
                qualified=True,
            )
        )
        db.commit()
        old = published(
            db,
            name="Old applied",
            settings=settings(provider_settings={"zone": "test-b"}),
        )
        service.bind(
            db,
            db.get(Engine, "engine-a"),
            C.Bind(
                version=0,
                feature="transcription",
                revision_id=old["latest_published_revision_id"],
            ),
            "bootstrap",
        )
        db.query(RuntimeProfile).one().applied_at = datetime.utcnow()
        db.commit()
        new = published(db, name="New desired")
        grant(db, role="runtime_configurator")
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            service.bind(
                db,
                db.get(Engine, "engine-a"),
                C.Bind(
                    version=1,
                    feature="transcription",
                    revision_id=new["latest_published_revision_id"],
                ),
                "operator",
            )
        db.rollback()
        assert db.query(RuntimeProfile).count() == 1


def test_source_revision_must_be_published_and_hash_must_match_even_in_domain(world):
    with world() as db:
        grant(db, role="runtime_configurator")
        p = draft(db)
        r = db.get(ExecutionRevision, p["revisions"][0]["id"])
        with pytest.raises(control.ControlError, match="PUBLISHED_REVISION_REQUIRED"):
            control.save_profile(
                db,
                db.get(Engine, "engine-a"),
                "transcription",
                settings(),
                0,
                "operator",
                source_profile_revision_id=r.id,
                source_hash=r.content_hash,
            )
        db.rollback()
        p = service.publish(
            db, p["id"], C.Publish(version=p["version"], revision_id=r.id), "bootstrap"
        )
        with pytest.raises(control.ControlError, match="PUBLISHED_REVISION_REQUIRED"):
            control.save_profile(
                db,
                db.get(Engine, "engine-a"),
                "transcription",
                settings(),
                0,
                "operator",
                source_profile_revision_id=r.id,
                source_hash="fabricated",
            )


def test_runner_never_calls_provider_for_actor_revoked_after_enqueue(
    world, monkeypatch
):
    from workers.engine_control.runner import run

    calls = []
    monkeypatch.setattr(
        Provider,
        "apply",
        lambda self, plan, ctx: calls.append("external-effect"),
        raising=False,
    )
    with world() as db:
        g, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        service.revoke(db, g["id"], 0, "bootstrap")
    run(op["operation_id"], world)
    with world() as db:
        row = db.get(EngineOperation, op["operation_id"])
        assert row.state == "failed" and not row.effect_started
        assert calls == []
        assert db.query(EffectAdmission).count() == 0
        assert db.get(ControlResource, RESOURCE).operation_id is None


def test_runner_stops_next_effect_after_revoke_and_preserves_uncertain_exposure(
    world, monkeypatch
):
    from workers.engine_control.runner import run

    calls = []
    with world() as db:
        g, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)

    def apply(self, plan, ctx):
        ctx.admit_effect("sdk:first")
        calls.append("first-admitted-effect")
        with world() as db:
            service.revoke(db, g["id"], 0, "bootstrap")
        ctx.admit_effect("sdk:second")
        calls.append("forbidden-second-effect")
        return {"ready_replicas": 1, "replicas_alive": 1}

    monkeypatch.setattr(Provider, "apply", apply, raising=False)
    run(op["operation_id"], world)
    with world() as db:
        row = db.get(EngineOperation, op["operation_id"])
        assert calls == ["first-admitted-effect"]
        assert row.state == "needs_attention" and row.effect_started
        assert db.query(EffectAdmission).one().state == "uncertain"
        assert db.get(ControlResource, RESOURCE).operation_id == row.id
        assert db.query(RuntimeProfile).one().applied_at is None
        assert db.get(Engine, "engine-a").config["features"] == {}


def test_open_sse_connection_stops_delivering_operation_events_after_revocation(
    world, monkeypatch
):
    import asyncio
    from types import SimpleNamespace
    from api import engine_control_routes
    import shared.auth

    with world() as db:
        _, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        observer = grant(db, actor="observer", role="observer")
        user = db.get(User, "observer")
        db.expunge(user)
    monkeypatch.setattr(engine_control_routes, "SessionLocal", world)
    monkeypatch.setattr(shared.auth, "verify_token", lambda token: "observer")

    async def disconnected():
        return False

    request = SimpleNamespace(
        headers={"authorization": "Bearer mocked-valid-session"},
        is_disconnected=disconnected,
    )

    async def consume():
        response = await engine_control_routes.stream(
            op["operation_id"], request, user=user
        )
        first = await response.body_iterator.__anext__()
        assert "event: operation" in first
        with world() as db:
            service.revoke(db, observer["id"], 0, "bootstrap")
            row = db.get(EngineOperation, op["operation_id"])
            control.append_event(
                db, row, "private.after-revoke", {"message": "must not arrive"}
            )
            db.commit()
        remaining = [chunk async for chunk in response.body_iterator]
        assert not any("event: operation" in chunk for chunk in remaining)
        assert "must not arrive" not in "".join(remaining)

    asyncio.run(consume())


def test_domain_rejects_raw_settings_mismatching_published_source(world):
    with world() as db:
        p = published(db)
        r = db.get(ExecutionRevision, p["latest_published_revision_id"])
        grant(db, role="runtime_configurator")
        with pytest.raises(control.ControlError, match="PROFILE_CONTENT_MISMATCH"):
            control.save_profile(
                db,
                db.get(Engine, "engine-a"),
                "transcription",
                settings(desired_replicas=2),
                0,
                "operator",
                source_profile_revision_id=r.id,
                source_hash=r.content_hash,
            )
        db.rollback()
        assert db.query(RuntimeProfile).count() == 0


@pytest.fixture
def legacy_provider(world, monkeypatch):
    from workers.engines import remote, remote_tasks
    from workers.engines.base import HealthReport

    calls = []
    callback = {"fn": None}

    class ReadOnlyProvider:
        def __init__(self, engine):
            self.engine = engine

        def test_connection(self):
            calls.append(self.engine.id)
            if callback["fn"]:
                callback["fn"]()
            return HealthReport(
                True,
                None,
                "Synthetic connection",
                deployed=True,
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

    monkeypatch.setattr(remote, "open_credentials", lambda engine: {})
    monkeypatch.setattr(
        remote, "adapter_factory", lambda engine, credentials: ReadOnlyProvider(engine)
    )
    monkeypatch.setattr(get_settings(), "engine_installation_principal_id", "")
    with world() as db:
        for engine in db.query(Engine):
            engine.credentials_sealed = b"synthetic-sealed-no-secret"
        db.commit()
    return remote_tasks, calls, callback


def legacy_context(db, ids=None):
    from shared.access import legacy

    ids = ids or ["engine-a"]
    g = grant(db, scope=constraints(engine_ids=ids))
    context = legacy.accept(db, "operator", "test", [db.get(Engine, id) for id in ids])
    return g, context


def test_legacy_task_uses_frozen_ids_and_rejects_modified_envelope(
    world, legacy_provider
):
    tasks, calls, _ = legacy_provider
    with world() as db:
        _, context = legacy_context(db)
    reports = tasks.test_all_now(
        session_factory=world, engine_ids=["engine-a"], authorization=context
    )
    assert list(reports) == ["engine-a"] and reports["engine-a"]["ok"]
    assert calls == ["engine-a"]
    with pytest.raises(control.ControlError, match="LEGACY_CONTEXT_INVALID"):
        tasks.test_all_now(
            session_factory=world, engine_ids=["engine-b"], authorization=context
        )
    assert calls == ["engine-a"]


@pytest.mark.parametrize("change", ["revoke", "deactivate"])
def test_legacy_revalidates_before_opening_provider_sdk(world, legacy_provider, change):
    tasks, calls, _ = legacy_provider
    with world() as db:
        g, context = legacy_context(db)
        if change == "revoke":
            service.revoke(db, g["id"], 0, "bootstrap")
        else:
            db.get(User, "operator").is_active = False
            db.commit()
    with pytest.raises(control.ControlError, match="ACCESS_DENIED|ACCESS_REVOKED"):
        tasks.test_engine_now("engine-a", session_factory=world, authorization=context)
    assert calls == []


def test_legacy_revalidates_before_record_and_never_tests_next_engine_after_revoke(
    world, legacy_provider
):
    tasks, calls, callback = legacy_provider
    with world() as db:
        g, context = legacy_context(db, ["engine-a", "engine-b"])

    def revoke():
        with world() as db:
            service.revoke(db, g["id"], 0, "bootstrap")

    callback["fn"] = revoke
    with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
        tasks.test_all_now(
            session_factory=world,
            engine_ids=["engine-a", "engine-b"],
            authorization=context,
        )
    assert calls == ["engine-a"]
    with world() as db:
        assert "last_test" not in db.get(Engine, "engine-a").config
        assert "last_test" not in db.get(Engine, "engine-b").config


def test_legacy_direct_cli_requires_registered_installation_principal_before_sdk(
    world, legacy_provider
):
    tasks, calls, _ = legacy_provider
    with pytest.raises(control.ControlError, match="INSTALLATION_PRINCIPAL_REQUIRED"):
        tasks.test_engine_now("engine-a", session_factory=world)
    assert calls == []


def test_connection_manager_can_clear_scoped_credentials_without_generic_admin_writes(
    world,
):
    from shared.engines import store

    with world() as db:
        grant(db, role="connection_manager")
        engine = db.get(Engine, "engine-a")
        engine.credentials_sealed = b"synthetic"
        db.commit()
        store.clear_credentials(
            db, engine, version=0, actor_user_id="operator", auth_method="jwt"
        )
        assert engine.credentials_sealed is None and engine.version == 1
        with pytest.raises(store.EngineStateError, match="ACCESS_DENIED"):
            store.clear_credentials(
                db,
                db.get(Engine, "engine-b"),
                version=0,
                actor_user_id="operator",
                auth_method="jwt",
            )
        db.rollback()
        with pytest.raises(store.EngineStateError, match="ACCESS_DENIED"):
            store.set_status(
                db,
                db.get(Engine, "engine-a"),
                "paused",
                version=1,
                actor_user_id="operator",
                auth_method="jwt",
            )


def test_operator_cannot_clear_credentials_through_direct_domain_call(world):
    from shared.engines import store

    with world() as db:
        grant(db)
        engine = db.get(Engine, "engine-a")
        engine.credentials_sealed = b"synthetic"
        db.commit()
        with pytest.raises(store.EngineStateError, match="ACCESS_DENIED"):
            store.clear_credentials(
                db, engine, version=0, actor_user_id="operator", auth_method="jwt"
            )
        db.rollback()
        assert engine.credentials_sealed == b"synthetic" and engine.version == 0


def test_subject_state_changes_bump_epoch_and_reject_stale_expected_state(
    world, client
):
    http, actor = client
    with world() as db:
        grant(db, actor="observer", role="observer")
        old_epoch = db.get(AuthorizationEpoch, 1).version
    body = dict(
        expected_is_active=True,
        expected_is_admin=False,
        is_active=False,
        is_admin=False,
    )
    response = http.put(
        "/admin/access/subjects/observer/state", headers=HEADERS, json=body
    )
    assert response.status_code == 200, response.text
    with world() as db:
        assert db.get(AuthorizationEpoch, 1).version == old_epoch + 1
        assert not policy.allowed(
            db, "observer", "engines.read", engine=db.get(Engine, "engine-a")
        )
    response = http.put(
        "/admin/access/subjects/observer/state", headers=HEADERS, json=body
    )
    assert response.status_code == 409
    with world() as db:
        assert db.get(AuthorizationEpoch, 1).version == old_epoch + 1
    actor["id"] = "operator"
    with world() as db:
        grant(db)
    assert (
        http.put(
            "/admin/access/subjects/outsider/state", headers=HEADERS, json=body
        ).status_code
        == 403
    )


@pytest.mark.parametrize("boundary", ["plan", "enqueue", "effect"])
@pytest.mark.parametrize("change", ["changed", "unapproved"])
def test_catalog_drift_is_rechecked_at_each_execution_boundary(world, boundary, change):
    with world() as db:
        _, p = prepared(db)
        op = None
        if boundary == "effect":
            op = control.enqueue(
                db, p["plan_id"], p["plan_hash"], "once", "operator", True
            )
            gen = control.claim(db, op["operation_id"], "executor")
        model = registry.descriptor(ADAPTER)["model_profiles"][0]
        model["model" if change == "changed" else "approved"] = (
            "new-model" if change == "changed" else False
        )
        with pytest.raises(control.ControlError, match="MODEL_METADATA_CHANGED"):
            if boundary == "plan":
                control.create_plan(
                    db,
                    db.get(Engine, "engine-a"),
                    PlanRequest(type="scale", engine_version=1, max_usd="0.10"),
                    "operator",
                )
            elif boundary == "enqueue":
                control.enqueue(
                    db, p["plan_id"], p["plan_hash"], "once", "operator", True
                )
            else:
                control.admit_effect(db, op["operation_id"], gen, "sdk:changed-model")
        db.rollback()
        assert db.query(EffectAdmission).count() == 0
        assert db.query(EngineOperation).count() == (1 if boundary == "effect" else 0)


def test_capabilities_discovery_selects_only_authorized_feature_and_models(
    world, client
):
    http, actor = client
    descriptor = registry.descriptor(ADAPTER)
    descriptor["features"] = descriptor["features"] + ["vision"]
    descriptor["model_profiles"] = descriptor["model_profiles"] + [
        dict(
            id="approved-vision",
            title="Approved vision",
            feature="vision",
            adapters=[ADAPTER],
            approved=True,
            model="vision-model",
            footprint_gb=1,
        )
    ]
    with world() as db:
        grant(db, scope=constraints(features=["vision"], model_ids=["approved-vision"]))
        db.add(
            RuntimeProfile(
                engine_id="engine-a",
                feature="transcription",
                revision=1,
                profile=settings(),
            )
        )
        db.commit()
    actor["id"] = "operator"
    response = http.get("/admin/engines/engine-a/capabilities", headers=HEADERS)
    assert response.status_code == 200, response.text
    caps = response.json()
    assert caps["features"] == ["vision"]
    assert (
        caps["managed"] is False
    ), "A private transcription profile must not influence vision discovery"
    assert {m["id"] for m in caps["model_profiles"]} == {"approved-vision"}
    assert "approved-profile-test" not in response.text
    assert (
        http.get(
            "/admin/engines/engine-a/capabilities?feature=transcription",
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert {
        m["id"] for m in http.get("/admin/model-profiles", headers=HEADERS).json()
    } == {"approved-vision"}


def test_capabilities_hide_managed_state_for_runtime_with_private_model_identity(
    world, client
):
    http, actor = client
    with world() as db:
        grant(db, scope=constraints(model_ids=["another-allowed-model"]))
        db.add(
            RuntimeProfile(
                engine_id="engine-a",
                feature="transcription",
                revision=1,
                profile=settings(),
            )
        )
        db.commit()
    actor["id"] = "operator"
    response = http.get("/admin/engines/engine-a/capabilities", headers=HEADERS)
    assert response.status_code == 200
    assert not response.json()["managed"]
    assert all(a["reason"] == "ACCESS_DENIED" for a in response.json()["actions"])
    assert response.json()["model_profiles"] == []


@pytest.mark.parametrize("terminal", ["succeeded", "needs_attention"])
def test_effect_metadata_records_executor_scope_and_only_confirmed_success_resolves_it(
    world, terminal
):
    with world() as db:
        g, p = prepared(db)
        result = control.enqueue(
            db, p["plan_id"], p["plan_hash"], "once", "operator", True
        )
        op_id = result["operation_id"]
        generation = control.claim(db, op_id, "registered-executor")
        control.admit_effect(db, op_id, generation, "sdk:scale")
        db.commit()
        op = db.get(EngineOperation, op_id)
        admission = db.query(EffectAdmission).one()
        assert (
            admission.actor_id == "operator"
            and admission.executor == "registered-executor"
        )
        assert admission.action == "scale" and admission.targets == p["resources"]
        assert admission.decision["grant_id"] == g["id"]
        assert (
            admission.valid_until == op.deadline
            and admission.epoch == admission.decision["epoch"]
        )
        control.finish(
            db,
            op_id,
            generation,
            terminal,
            {"replicas_alive": 1},
            safe=terminal == "succeeded",
        )
        db.refresh(admission)
        assert admission.state == (
            "confirmed" if terminal == "succeeded" else "uncertain"
        )
        assert (
            op.cost_confirmed is False
        ), "Admission confirmation cannot invent provider billing confirmation"
