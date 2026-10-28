"""Opt-in of the local idle cooldown (spec 0007 §4.6) and the actor its automatic operations use.

The idle policy has no identity of its own: each automatic cooldown/start runs as the admin
whose apply_profile operation applied the revision with `idle_cooldown=true` (a scheduled task
runs as whoever scheduled it), through the same create_plan/enqueue/authorize. So the opt-in is
refused unless that admin may plan, cool down and start the engine, and only local engines with
a dedicated service per feature qualify (document conversion shares the generic worker with the
default queue; standing it by would stop those queues too).
"""

from typing import NamedTuple, Optional

from shared.engine_control.models import EngineOperation, OperationPlan, RuntimeProfile

IDLE_FEATURES = frozenset({"transcription", "vision"})
IDLE_PERMISSIONS = frozenset(
    {"engine_operations.plan", "engine_operations.execute.cooldown", "engine_operations.execute.start"}
)


class OptIn(NamedTuple):
    actor: str
    revision: int  # pass it as PlanRequest.profile_revision: never the newer, unapplied desire


def require(db, engine, feature, runtime, actor, resources, *, profile=None) -> None:
    """Refuse `idle_cooldown=true` off a local transcription/vision engine, or for an actor
    who could not later run the automatic cooldown and start. `profile` is the published
    execution profile the runtime came from (grants may be scoped to it)."""
    if not (runtime or {}).get("idle_cooldown"):
        return
    from shared.access import policy
    from shared.engine_control.service import ControlError

    if engine.adapter_type != "local" or feature not in IDLE_FEATURES:
        raise ControlError("IDLE_COOLDOWN_NOT_SUPPORTED", 422, feature=feature)
    if not policy.enabled():
        return
    try:
        policy.authorize(db, actor, set(IDLE_PERMISSIONS), engine=engine, feature=feature,
                         runtime=runtime, profile=profile, resources=resources)
    except ControlError as exc:
        if exc.code != "ACCESS_DENIED":  # revoked access, schema not ready: keep their own code
            raise
        raise ControlError("IDLE_COOLDOWN_PERMISSION_REQUIRED", 403, feature=feature) from None


def opt_in(db, engine_id: str, feature: str) -> Optional[OptIn]:
    """Who the automatic operations of this feature run as, and on which revision: the actor
    of the latest successful apply_profile of the applied revision, when that revision opted
    in. None when it did not, or when no apply_profile applied it (the policy does nothing)."""
    applied = (
        db.query(RuntimeProfile)
        .filter_by(engine_id=engine_id, feature=feature)
        .filter(RuntimeProfile.applied_at.isnot(None))
        .order_by(RuntimeProfile.applied_at.desc())
        .first()
    )
    if applied is None or not (applied.profile or {}).get("idle_cooldown"):
        return None
    actor = (
        db.query(EngineOperation.actor_id)
        .join(OperationPlan, OperationPlan.id == EngineOperation.plan_id)
        .filter(EngineOperation.engine_id == engine_id, EngineOperation.state == "succeeded",
                OperationPlan.profile_id == applied.id,
                OperationPlan.body["type"].as_string() == "apply_profile")
        .order_by(EngineOperation.finished_at.desc())
        .limit(1)
        .scalar()
    )
    return OptIn(actor, applied.revision) if actor else None
