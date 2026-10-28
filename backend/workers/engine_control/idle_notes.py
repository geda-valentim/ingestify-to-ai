"""What the idle policy tells the admin, and the refusals it remembers (spec 0007, section 4.6).

Both notes (a refused actor, an exhausted wakeup) go on the operation that applied the
opt-in, where the admin looks, written by the system and never in the opt-in admin's name:
the audit trail must not say that admin did something they did not do. Each is written
once per applied state, deduplicated on that operation under its row lock, not by Redis.
"""

import logging

from shared.engine_control import service
from shared.engine_control.models import EngineOperation, OperationEvent, OperationPlan

logger = logging.getLogger(__name__)

SYSTEM_AUTHOR = "system:idle_policy"
WAKEUP_GAVE_UP = "idle_policy.wakeup_gave_up"
REFUSED_EVENT = "idle_policy.refused"

# A refused actor (403: the opt-in's admin lost the permission) is not asked
# again for the same applied state. The key only suppresses attempts, it never
# authorizes anything: if it is lost, one more attempt is made and refused again
# by the database. A new applied state is a new key.
REFUSAL_TTL_SECONDS = 24 * 3600


def applied_state(profile):
    return f"{profile.revision}:{profile.applied_at:%Y%m%dT%H%M%S%f}"


def refusal_key(engine_id, feature, profile, actor):
    return f"engine_idle:refused:{engine_id}:{feature}:{applied_state(profile)}:{actor}"


def _redis():
    from shared.redis_client import get_redis_client

    return get_redis_client().client


def refusal_known(key):
    try:
        return bool(_redis().exists(key))
    except Exception:  # noqa: BLE001 - no suppression; the database refuses again
        return False


def remember_refusal(key):
    """True only for the call that created the key."""
    try:
        return bool(_redis().set(key, "1", nx=True, ex=REFUSAL_TTL_SECONDS))
    except Exception:  # noqa: BLE001
        return False


def _opt_in_operation(db, engine_id, profile, actor):
    """The latest successful apply_profile of this revision by the opt-in's actor (as opt_in() finds it)."""
    return (
        db.query(EngineOperation.id)
        .join(OperationPlan, OperationPlan.id == EngineOperation.plan_id)
        .filter(EngineOperation.engine_id == engine_id, EngineOperation.actor_id == actor,
                EngineOperation.state == "succeeded", OperationPlan.profile_id == profile.id,
                OperationPlan.body["type"].as_string() == "apply_profile")
        .order_by(EngineOperation.finished_at.desc())
        .first()
    )


def _note(db, engine_id, feature, profile, actor, event, payload):
    """Write `event` once per applied state on the opt-in operation; False if there is none."""
    found = _opt_in_operation(db, engine_id, profile, actor)
    if found is None:
        logger.warning("engine idle policy: %s on %s/%s; no opt-in operation to note it on",
                       event, engine_id, feature)
        return False
    op = db.query(EngineOperation).filter_by(id=found.id).with_for_update().one()
    state = applied_state(profile)
    noted = db.query(OperationEvent.payload).filter_by(operation_id=op.id, type=event).all()
    if any((row.payload or {}).get("state") == state for row in noted):
        db.rollback()
        return True
    service.append_event(db, op, event, dict(payload, state=state, author=SYSTEM_AUTHOR))
    db.commit()
    return True


def announce_refusal(db, engine_id, feature, profile, actor, action, code):
    return _note(db, engine_id, feature, profile, actor, REFUSED_EVENT, {
        "message": (
            "A política de ociosidade parou: o administrador que ativou o cooldown automático não tem mais "
            "permissão para operar esta engine. Reaplique o perfil com um administrador autorizado."
        ),
        "action": action,
        "code": code,
    })


def give_up(db, engine_id, feature, profile, actor, attempts, waiting):
    """Once per exhausted wakeup: the reason the queue is not moving."""
    return _note(db, engine_id, feature, profile, actor, WAKEUP_GAVE_UP, {
        "message": (
            f"O despertar automático desistiu após {attempts} tentativas; "
            f"{int(waiting)} trabalhos esperando. Inicie o serviço pelo painel para retomar."
        ),
        "waiting": int(waiting),
    })
