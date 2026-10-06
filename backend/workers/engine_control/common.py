from datetime import datetime, timedelta
from decimal import Decimal
from shared.engine_control import catalog, registry
from shared.engine_control.service import ControlError
from shared.engine_control.contracts import utc_deadline
from shared.engines.capacity import Binding, validate_engine_config


def validate(engine, feature, p, db):
    d = registry.descriptor(engine.adapter_type, p["adapter_version"])
    if feature not in d["features"]:
        raise ValueError("FEATURE_UNSUPPORTED")
    model = catalog.get(p["model_profile_id"], engine.adapter_type, feature)
    # Nested Binding historically ignores extra keys: prohibit them in the new contract.
    if set(p["binding"]) - set(Binding.model_fields):
        raise ValueError("Unknown binding field")
    binding = Binding(**p["binding"])
    if (binding.gpu_ref or binding.gpu_type) and model["footprint_gb"] is None:
        raise ValueError("MODEL_FOOTPRINT_NOT_QUALIFIED")
    if model["footprint_gb"]:
        binding.vram_override_gb = model["footprint_gb"]
    p = dict(p, binding=binding.model_dump(exclude_none=True), model=model)
    config = dict(engine.config or {})
    features = dict(config.get("features") or {})
    if feature != "live-transcription":
        features[feature] = p["binding"]
    config["features"] = features
    validate_engine_config(engine.adapter_type, config)
    if p["warm_until"]:
        until = utc_deadline(p["warm_until"])
        if not datetime.utcnow() < until <= datetime.utcnow() + timedelta(hours=24):
            raise ValueError("Warm deadline must be in the next 24 hours")
    if (
        p["min_ready_replicas"]
        and engine.adapter_type != "local"
        and not p["warm_until"]
    ):
        raise ValueError("WARM_EXPIRATION_REQUIRED")
    return p


def plan(engine, req, p, db):
    d = registry.descriptor(engine.adapter_type)
    if req.type not in d["actions"]:
        raise ValueError("ACTION_UNSUPPORTED")
    return dict(
        stages=["validating", "draining", "applying", "verifying"],
        drain=req.type not in ("test", "reconcile"),
        destructive=d["stop_destructive"] and req.type == "drain_stop",
        estimated_max_usd="0",
        effects=[req.type],
        description="Executar e verificar estado real",
    )
