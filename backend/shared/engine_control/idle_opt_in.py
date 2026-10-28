"""Opt-in of the local idle cooldown (spec 0007 §4.6) and the actor its automatic operations use.

The idle policy has no identity of its own: each automatic cooldown/start runs as the admin
whose apply_profile operation applied the revision with `idle_cooldown=true` (a scheduled task
runs as whoever scheduled it), through the same create_plan/enqueue/authorize. So the opt-in is
refused unless that admin may plan, cool down and start the engine, and only local engines with
a dedicated service per feature qualify (document conversion shares the generic worker with the
default queue; standing it by would stop those queues too). An automatic plan is checked again
against the opt-in it claims, and its actor re-authorized even with IAM off (an admin who was
deactivated or demoted since the opt-in no longer lends their identity).
"""

from typing import NamedTuple, Optional

from shared.engine_control.models import ControlResource, EngineOperation, OperationPlan, RuntimeProfile

IDLE_FEATURES = frozenset({"transcription", "vision"})
# Two authorities, each checkable against one grant: cool down, and start again.
IDLE_PERMISSIONS = (
    frozenset({"engine_operations.plan", "engine_operations.execute.cooldown"}),
    frozenset({"engine_operations.plan", "engine_operations.execute.start"}),
)
AUTOMATIC = {"idle_policy": "cooldown", "wakeup": "start"}  # trigger -> the only type it may plan
# The recovery of an automatic operation proved its effect never happened: failed, nothing repeated.
NOT_APPLIED = {"code": "AUTOMATIC_EFFECT_NOT_APPLIED"}  # message and next steps: the error catalog


class OptIn(NamedTuple):
    actor: str
    revision: int  # pass it as PlanRequest.profile_revision: never the newer, unapplied desire


def refuse_unsupported(adapter_type, feature, runtime):
    """On save of an execution profile: idle_cooldown=true only for local transcription/vision."""
    from shared.engine_control.service import ControlError

    if (runtime or {}).get("idle_cooldown") and (adapter_type != "local" or feature not in IDLE_FEATURES):
        raise ControlError("IDLE_COOLDOWN_NOT_SUPPORTED", 422, feature=feature)


def _qualifies(engine, feature):
    from shared.engine_control.service import ControlError

    if engine.adapter_type != "local" or feature not in IDLE_FEATURES:
        raise ControlError("IDLE_COOLDOWN_NOT_SUPPORTED", 422, feature=feature)


def require(db, engine, feature, runtime, actor, resources, *, profile=None) -> None:
    """Refuse `idle_cooldown=true` off a local transcription/vision engine, or for an actor
    who could not later run the automatic cooldown and start. `profile` is the published
    execution profile the runtime came from (grants may be scoped to it)."""
    if not (runtime or {}).get("idle_cooldown"):
        return
    from shared.access import policy
    from shared.engine_control.service import ControlError

    _qualifies(engine, feature)
    if not policy.enabled():
        return
    try:
        for permissions in IDLE_PERMISSIONS:
            policy.authorize(db, actor, set(permissions), engine=engine, feature=feature,
                             runtime=runtime, profile=profile, resources=resources, lock=True)
    except ControlError as exc:
        if exc.code != "ACCESS_DENIED":  # revoked access, schema not ready: keep their own code
            raise
        raise ControlError("IDLE_COOLDOWN_PERMISSION_REQUIRED", 403, feature=feature) from None


def _authorize_actor(db, actor) -> None:
    """With IAM off (where the domain call otherwise authorizes nothing), the opt-in actor must
    still pass the rule the API applies to every human request: an active, effective admin. Not
    authorize(force=True): it needs the access schema, which an installation with IAM off may
    not have (a test proves both rules agree). With IAM on, the plan's own authorization holds."""
    from shared.access import policy
    from shared.admin import is_effective_admin
    from shared.engine_control.service import ControlError
    from shared.models import User

    if policy.enabled():
        # create_plan/enqueue already authorize this actor with the full scope (source profile,
        # max_usd, lock), and the effect is admitted again; a partial second check here would
        # only refuse profile-scoped grants.
        return
    user = db.query(User).filter_by(id=str(actor)).populate_existing().with_for_update().first()
    if user is None or not user.is_active or not is_effective_admin(user):
        raise ControlError("ACCESS_REVOKED", 403)


def _check(db, engine, feature, type_, trigger, actor, revision) -> None:
    """The one rule for an automatic operation, at every point from its plan to its effect
    (spec 0007 §4.6): it only cools down (idle_policy) or starts (wakeup) a local
    transcription/vision engine, as the actor and on the revision of the opt-in in force, and
    that actor is still authorized (with IAM off: active, effective admin)."""
    from shared.engine_control.service import ControlError

    _qualifies(engine, feature)
    if AUTOMATIC.get(trigger) != type_ or opt_in(db, engine.id, feature) != (actor, revision):
        raise ControlError("IDLE_POLICY_NOT_OPTED_IN", 403, feature=feature)
    _authorize_actor(db, actor)


def check_automatic(db, engine, req, actor, runtime, resources) -> None:
    """At create_plan, for a TriggeredPlanRequest."""
    _check(db, engine, req.feature, req.type, getattr(req, "trigger", None), actor, req.profile_revision)


def check_plan(db, plan) -> None:
    """The same rule for a stored plan: at enqueue, at claim and right before each external
    effect (an opt-in revoked or an actor deactivated in between stops it there). Human plans
    are not concerned."""
    body = plan.body or {}
    if not body.get("trigger"):
        return
    from shared.models import Engine

    _check(db, db.get(Engine, plan.engine_id), body["feature"], body["type"], body["trigger"],
           plan.actor_id, body.get("profile_revision"))


def reauthorize_automatic(db, plan_id, actor) -> None:
    """At enqueue (the plan's own actor; a foreign plan is refused by the caller)."""
    plan = db.get(OperationPlan, plan_id)
    if plan is not None and plan.actor_id == actor:
        check_plan(db, plan)


def refusal_at_claim(db, op):
    """At claim: None, or the error with which the automatic operation ends before any effect."""
    from shared.engine_control.service import ControlError

    try:
        check_plan(db, db.get(OperationPlan, op.plan_id))
    except ControlError as exc:
        return {"code": exc.code, "message": "A operação automática deixou de valer antes do efeito."}
    return None


def check_before_effect(db, op_id) -> None:
    """Right before an external effect (admit_effect), even with IAM off."""
    op = db.get(EngineOperation, op_id)
    if op is not None:
        check_plan(db, db.get(OperationPlan, op.plan_id))


def opt_in(db, engine_id: str, feature: str) -> Optional[OptIn]:
    """Who the automatic operations of this feature run as, and on which revision: the actor
    of the latest successful apply_profile of the currently applied revision, when that
    revision opted in and nothing else was applied since (applied_state keeps the reference
    only while the same revision stays applied, so re-applying an old opted-in revision by
    any other type does not revive it).

    Read from the resources' applied state and then by primary key, never from the
    operation history: it runs on every tick of the idle policy. A resource without the
    reference (written before it existed) has no opt-in until the profile is applied
    again; references that disagree fail closed. None: the policy does nothing.
    """
    found = opt_in_reference(db, engine_id, feature)
    return found[1] if found else None


def opt_in_reference(db, engine_id: str, feature: str):
    """(id of the apply_profile operation that opted in, OptIn), or None: see opt_in()."""
    applied = (
        db.query(RuntimeProfile)
        .filter_by(engine_id=engine_id, feature=feature)
        .filter(RuntimeProfile.applied_at.isnot(None))
        .order_by(RuntimeProfile.applied_at.desc())
        .first()
    )
    if applied is None or not (applied.profile or {}).get("idle_cooldown"):
        return None
    # One row per resource of the engine (a handful), not a history.
    rows = db.query(ControlResource.applied).filter(ControlResource.owner_engine_id == engine_id).all()
    refs = {
        ((row.applied or {}).get("opt_in_operation_id"), (row.applied or {}).get("opt_in_actor"))
        for row in rows
        if (row.applied or {}).get("profile_id") == applied.id
    }
    if len(refs) != 1:
        return None
    op_id, actor = refs.pop()
    op = db.get(EngineOperation, op_id) if op_id else None
    plan = db.get(OperationPlan, op.plan_id) if op else None
    if (op is None or op.state != "succeeded" or op.actor_id != actor or op.engine_id != engine_id
            or plan is None or plan.profile_id != applied.id or (plan.body or {}).get("type") != "apply_profile"):
        return None
    return op.id, OptIn(actor, applied.revision)
