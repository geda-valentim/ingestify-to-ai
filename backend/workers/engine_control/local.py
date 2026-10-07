from datetime import datetime, timedelta
from shared.engine_control import registry
from shared.engine_control.models import ControlHost
from workers.engine_control import common

SERVICES = {
    "transcription": "worker-audio",
    "document_conversion": "worker",
    "vision": "worker-vision",
    "live-transcription": "worker-live",
}


class LocalControlAdapter:
    def describe(self):
        return registry.descriptor("local")

    def resource_keys(self, engine, feature, p):
        host = (p.get("provider_settings") or {}).get("host_id", "unregistered")
        keys = [f"local:{host}:service:{SERVICES.get(feature,feature)}"]
        # Legacy media can execute on the generic worker as well.
        if feature in ("transcription", "vision"):
            keys.append(f"local:{host}:service:worker")
        if (p.get("binding") or {}).get("gpu_ref"):
            gpu = next(
                (
                    g
                    for g in (engine.config or {}).get("gpus", [])
                    if g["ref"] == p["binding"]["gpu_ref"]
                ),
                None,
            )
            uuid = p.get("gpu_uuid") or (gpu.get("uuid") or gpu["ref"] if gpu else None)
            if uuid:
                keys.append(f"local:{host}:gpu:{uuid}")
        return sorted(keys)

    def validate(self, engine, feature, p, db):
        p = common.validate(engine, feature, p, db)
        if set(p["provider_settings"]) != {"host_id"}:
            raise ValueError("Provider settings require only host_id")
        host = db.get(ControlHost, p["provider_settings"]["host_id"])
        if not host or host.seen_at < datetime.utcnow() - timedelta(seconds=30):
            raise ValueError("HOST_AGENT_NOT_READY")
        service = SERVICES[feature]
        if feature == "live-transcription":
            if p["binding"]["executions_per_worker"] != 1 or p["max_replicas"] > 1:
                raise ValueError("LIVE_SINGLE_RESIDENT_REQUIRED")
            if not p["binding"].get("gpu_ref"):
                raise ValueError("LIVE_REQUIRES_CUDA")
        if service not in host.inventory.get("services", []):
            raise ValueError("SERVICE_NOT_REGISTERED")
        # Do not apply a GPU reference that cannot actually be pinned.
        ref = p["binding"].get("gpu_ref")
        if ref:
            gpu = next(
                (g for g in engine.config.get("gpus", []) if g["ref"] == ref), None
            )
            if (
                not gpu
                or not gpu.get("uuid")
                or gpu["uuid"] not in host.inventory.get("gpu_uuids", [])
            ):
                raise ValueError("GPU_UUID_NOT_REGISTERED")
            p["gpu_uuid"] = gpu["uuid"]
        p["service"] = service
        p["manifest_hash"] = host.inventory["manifest_hash"]
        return p

    def plan(self, engine, req, p, db):
        if not p:
            raise ValueError("RUNTIME_PROFILE_REQUIRED")
        resolved = self.validate(
            engine,
            req.feature,
            {
                k: v
                for k, v in p.items()
                if k not in ("model", "service", "gpu_uuid", "manifest_hash")
            },
            db,
        )
        if p.get("gpu_uuid") != resolved.get("gpu_uuid") or p.get(
            "manifest_hash"
        ) != resolved.get("manifest_hash"):
            raise ValueError("PROFILE_INVENTORY_CHANGED: rebind the desired profile")
        return dict(
            common.plan(engine, req, p, db),
            host_id=p["provider_settings"]["host_id"],
            service=p["service"],
            manifest_hash=p["manifest_hash"],
        )

    def apply(self, plan, context):
        return context.assign_host(plan["host_id"])

    def observe(self, engine, feature, profile, context):
        with context.Session() as db:
            from shared.engine_control.models import EngineOperation, OperationPlan

            op = db.get(EngineOperation, context.op_id)
            plan = dict(db.get(OperationPlan, op.plan_id).body)
            op.handles = dict(op.handles or {}, host_result=None, recovery_observe=True)
            db.commit()
        return context.assign_host(profile["provider_settings"]["host_id"])

    def reconcile(self, operation, observed):
        p = operation["plan"]
        expected = (
            0
            if p["type"] in ("cooldown", "drain_stop")
            else p["profile"]["desired_replicas"]
        )
        if p["type"] == "warmup":
            expected = max(expected, p["profile"]["min_ready_replicas"])
        ready = (
            observed.get("replicas_alive") == expected
            and (not expected or observed.get("ready_replicas") == expected)
            and (
                not expected
                or observed.get("model_profile_id") == p["profile"]["model_profile_id"]
            )
            and (not expected or observed.get("revision") == p["profile_revision"])
        )
        return {"desired_applied": ready, "safe_to_unlock": ready}

    def cancel(self, operation, context):
        return {"cancel_requested": True}
