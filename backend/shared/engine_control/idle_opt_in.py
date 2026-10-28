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

from shared.engine_control.models import EngineOperation, OperationPlan, RuntimeProfile

IDLE_FEATURES = frozenset({"transcription", "vision"})
# Two authorities, each checkable against one grant: cool down, and start again.
IDLE_PERMISSIONS = (
    frozenset({"engine_operations.plan", "engine_operations.execute.cooldown"}),
    frozenset({"engine_operations.plan", "engine_operations.execute.start"}),
)
AUTOMATIC = {"idle_policy": "cooldown", "wakeup": "start"}  # trigger -> the only type it may plan


class OptIn(NamedTuple):
    actor: str
    revision: int  # pass it as PlanRequest.profile_revision: never the newer, unapplied desire


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


def check_automatic(db, engine, req, actor, runtime, resources) -> None:
    """An automatic plan (TriggeredPlanRequest) only for the opt-in it claims: a local
    transcription/vision engine whose applied revision opted in, run as that opt-in's actor on
    that revision; and the actor re-authorized even with IAM off (active, still an admin)."""
    from shared.engine_control.service import ControlError

    _qualifies(engine, req.feature)
    if AUTOMATIC.get(getattr(req, "trigger", None)) != req.type:  # even if the model was bypassed
        raise ControlError("IDLE_POLICY_NOT_OPTED_IN", 403, feature=req.feature)
    if opt_in(db, engine.id, req.feature) != (actor, req.profile_revision):
        raise ControlError("IDLE_POLICY_NOT_OPTED_IN", 403, feature=req.feature)
    _authorize_actor(db, actor)


def reauthorize_automatic(db, plan_id, actor) -> None:
    """At enqueue, an automatic plan's actor is authorized again even with IAM off."""
    plan = db.get(OperationPlan, plan_id)
    if plan is None or not (plan.body or {}).get("trigger") or plan.actor_id != actor:
        return  # human plans keep their usual path; a foreign plan is refused there
    _authorize_actor(db, actor)


def opt_in(db, engine_id: str, feature: str) -> Optional[OptIn]:
    """Who the automatic operations of this feature run as, and on which revision: the actor
    of the latest successful apply_profile of the currently applied revision, when that
    revision opted in and no other revision was applied (published, whatever became of its
    operation) at or after that apply_profile finished. Re-applying an old opted-in revision by
    any other type (a start by someone else) does not revive its opt-in; a tie fails closed.
    None: the policy does nothing."""
    applied = (
        db.query(RuntimeProfile)
        .filter_by(engine_id=engine_id, feature=feature)
        .filter(RuntimeProfile.applied_at.isnot(None))
        .order_by(RuntimeProfile.applied_at.desc())
        .first()
    )
    if applied is None or not (applied.profile or {}).get("idle_cooldown"):
        return None
    granted = (
        db.query(EngineOperation.actor_id, EngineOperation.finished_at)
        .join(OperationPlan, OperationPlan.id == EngineOperation.plan_id)
        .filter(EngineOperation.engine_id == engine_id, EngineOperation.state == "succeeded",
                OperationPlan.profile_id == applied.id,
                OperationPlan.body["type"].as_string() == "apply_profile")
        .order_by(EngineOperation.finished_at.desc())
        .first()
    )
    if granted is None or granted.finished_at is None:
        return None
    since = (
        db.query(RuntimeProfile.id)
        .filter(RuntimeProfile.engine_id == engine_id, RuntimeProfile.feature == feature,
                RuntimeProfile.id != applied.id, RuntimeProfile.applied_at >= granted.finished_at)
        .first()
    )
    return None if since else OptIn(granted.actor_id, applied.revision)
