"""All existing administrative writers participate in managed resource locks."""

from shared.config import get_settings
from shared.engine_control.models import (
    RuntimeProfile,
    EngineOperation,
    ControlResource,
)
from shared.engine_control.service import TERMINAL
from shared.engines.store import VersionConflict
from shared.models import Engine


def before_write(
    db,
    engine,
    version=None,
    runtime=False,
    credentials=False,
    actor=None,
    auth_method=None,
):
    from shared.access import policy

    if policy.enabled():
        policy.epoch(db, True)
        try:
            if actor:
                if credentials:
                    keys = [
                        r.key
                        for r in db.query(ControlResource).filter_by(
                            owner_engine_id=engine.id
                        )
                    ]
                    policy.authorize(
                        db,
                        actor,
                        "engine_connections.credentials.manage",
                        engine=engine,
                        resources=keys,
                        lock=True,
                    )
                else:
                    from shared.access.service import bootstrap

                    bootstrap(db, actor)
            elif auth_method == "cli":
                from shared.access.legacy import installation

                installation(db)
            else:
                from shared.engine_control.service import ControlError

                raise ControlError("ACCESS_REVOKED", 403)
        except Exception as exc:
            from shared.engine_control.service import ControlError
            from shared.engines.store import EngineStateError

            if isinstance(exc, ControlError):
                raise EngineStateError(exc.code, exc.status) from None
            raise

    # CAS/serialization applies to legacy writers too, without introducing control-table reads.
    db.query(Engine).filter_by(id=engine.id).populate_existing().with_for_update().one()
    if version is not None and version != engine.version:
        raise VersionConflict("VERSION_CONFLICT: re-read the engine")
    if not get_settings().engine_control_enabled:
        return
    locked = (
        db.query(ControlResource)
        .filter_by(owner_engine_id=engine.id)
        .filter(ControlResource.operation_id.isnot(None))
        .first()
    )
    if locked:
        raise VersionConflict(
            "OPERATION_CONFLICT: resource is controlled by an active/uncertain operation"
        )
    managed = db.query(RuntimeProfile).filter_by(engine_id=engine.id).first()
    if not managed:
        return
    if runtime:
        raise VersionConflict(
            "RUNTIME_OPERATION_REQUIRED: save a runtime profile and execute a plan"
        )
    if credentials:
        for op in db.query(EngineOperation).filter_by(engine_id=engine.id):
            if (op.handles or {}).get("maintenance", {}).get("cleanup_required"):
                raise VersionConflict(
                    "CLEANUP_CREDENTIAL_REQUIRED: verify cooldown before rotating/removing credentials"
                )
