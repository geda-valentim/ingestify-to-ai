from datetime import datetime
from decimal import Decimal
import json
import sys
import tempfile
import time
from shared.engine_control import registry
from shared.engine_control.models import ControlResource
from shared.engine_control.contracts import utc_deadline
from shared.engines.capacity import Binding
from workers.engine_control import common


def pool_count(stats):
    # Modal 1.5 names these runners; older SDKs exposed num_total_containers.
    value = getattr(
        stats, "num_total_runners", getattr(stats, "num_total_containers", None)
    )
    if value is None:
        raise RuntimeError("POOL_OBSERVATION_UNAVAILABLE")
    return int(value)


class ModalControlAdapter:
    def describe(self):
        return registry.descriptor("modal")

    def resource_keys(self, engine, feature, p):
        identity = (engine.config or {}).get("control_identity")
        environment = (engine.config or {}).get("modal_environment") or "main"
        # test/reconcile before identity qualification have no deployment side effect.
        return [f"modal:{identity or engine.id}:{environment}:ingestify-whisper"]

    def validate(self, engine, feature, p, db):
        p = common.validate(engine, feature, p, db)
        if (engine.config or {}).get("whisperx_manifest"):
            raise ValueError("WHISPERX_CONTROL_PROFILE_NOT_QUALIFIED")
        if p["provider_settings"]:
            raise ValueError("Unknown Modal provider settings")
        if not (engine.config or {}).get("control_identity"):
            raise ValueError("TEST_CONNECTION_FIRST")
        from shared.engines.pricing import modal_decorator

        modal_decorator(
            dict(
                engine.config or {},
                control_fingerprint_version=2,
                control_memory_mb=p.get("memory_mb"),
            ),
            Binding(**p["binding"]),
        )
        return p

    def plan(self, engine, req, p, db):
        base = common.plan(engine, req, p, db)
        if req.type not in ("test", "reconcile"):
            if not engine.credentials_sealed:
                raise ValueError("CREDENTIALS_REQUIRED")
            cleanup = req.type in ("cooldown", "drain_stop")
            if req.max_usd <= 0 and not cleanup:
                raise ValueError("PAID_BUDGET_REQUIRED")
            # Reserve the declared cap conservatively. A reservation is not a provider bill cap.
            base["estimated_max_usd"] = "0" if cleanup else str(req.max_usd)
            if req.type in ("warmup", "start") and not p.get("warm_until"):
                raise ValueError("WARM_EXPIRATION_REQUIRED")
            if p.get("warm_until") and not cleanup:
                from shared.engines.pricing import rate_usd_per_s

                until = utc_deadline(p["warm_until"])
                seconds = max(0, (until - datetime.utcnow()).total_seconds()) + 120
                minimum = max(
                    p["min_ready_replicas"],
                    p["desired_replicas"] if req.type in ("warmup", "start") else 0,
                )
                required = (
                    rate_usd_per_s(engine.config or {}, Binding(**p["binding"]))
                    * Decimal(str(seconds))
                    * minimum
                    * Decimal("1.2")
                )
                if req.type in ("deploy", "apply_profile", "restart", "start"):
                    required += Decimal("0.03")
                if req.max_usd < required:
                    raise ValueError(
                        f"A janela de aquecimento exige um teto de pelo menos US$ {required:.4f} (com margem)"
                    )
            if req.type in ("scale", "warmup", "cooldown") and not (
                engine.deployments or {}
            ).get(req.feature, {}).get("control_protocol"):
                raise ValueError("CONTROL_REDEPLOY_REQUIRED")
            if req.type in ("deploy", "apply_profile", "restart"):
                from workers.engines.modal_apps.files import lock_is_hashed

                if not lock_is_hashed():
                    raise ValueError("HASHED_MODEL_LOCK_REQUIRED")
                from workers.engines.modal_apps.fingerprint import deploy_spec

                config = dict(engine.config or {})
                config["control_fingerprint_version"] = 2
                config["control_memory_mb"] = p.get("memory_mb")
                base["artifact_fingerprint"] = deploy_spec(
                    req.feature, config, Binding(**p["binding"])
                )["fingerprint"]
        return base

    def _adapter(self, engine):
        from workers.engines import remote

        return remote.adapter_factory(engine, remote.open_credentials(engine))

    def apply(self, plan, ctx):
        from shared.models import Engine
        from shared.engine_control import service
        from workers.engines import remote_tasks, modal_deploy
        from workers.engine_control.process import stream_run

        with ctx.Session() as db:
            engine = db.get(Engine, plan["engine_id"])
            db.expunge(engine)
        action = plan["type"]
        if action == "test":
            ctx.admit_effect("test:connection")
            result = remote_tasks.test_engine_now(
                engine.id,
                session_factory=ctx.Session,
                authorization={"operation_id": ctx.op_id, "generation": ctx.generation},
            )
            if not result.get("ok"):
                raise RuntimeError(result.get("code") or "TEST_FAILED")
            ctx.admit_effect("test:identity")
            adapter = self._adapter(engine)
            identity = adapter._state().hydrate(client=adapter.client()).object_id
            with ctx.Session() as db:
                from shared.access import policy
                from workers.engine_control.runner import Cancelled

                if policy.enabled():
                    policy.epoch(db, True)
                op = service.fenced(db, ctx.op_id, ctx.generation)
                policy.operation_authority(db, op, effect=policy.enabled())
                if op.cancel_requested:
                    raise Cancelled()
                if op.deadline <= service.now():
                    raise TimeoutError("OPERATION_DEADLINE")
                e = service.locked_engine(db, engine.id)
                config = dict(e.config or {})
                config["control_identity"] = identity
                e.config = config
                e.version += 1
                db.commit()
            return {"connection": result, "identity_verified": True}
        if action == "reconcile":
            return remote_tasks.reconcile_now(
                only=engine.id,
                session_factory=ctx.Session,
                authorization={"operation_id": ctx.op_id, "generation": ctx.generation},
                human=True,
            )
        p = plan["profile"]
        adapter = self._adapter(engine)
        if action in ("deploy", "apply_profile", "restart", "start"):
            ctx.event("deploying", "Build e deploy do artifact aprovado", effect=True)
            # Deploy from the frozen desired binding, never mutate the scheduler config early.
            entry = modal_deploy.deploy(
                engine.slug,
                plan["feature"],
                session_factory=ctx.Session,
                run=lambda *a, **k: stream_run(*a, **k, context=ctx),
                out=ctx.log,
                control_profile=p,
                operation_id=ctx.op_id,
                effect_admission=ctx.admit_effect,
            )
            ctx.handles({"deployment": entry})
            engine.deployments = dict(
                engine.deployments or {}, **{plan["feature"]: entry}
            )
            adapter = self._adapter(engine)
        obj = adapter._runner()
        if not hasattr(obj, "update_autoscaler"):
            raise RuntimeError("SDK_AUTOSCALER_UNAVAILABLE")
        ctx.event("scaling", "Aplicando política do autoscaler", effect=True)
        cold = action in ("cooldown", "drain_stop")
        minimum = 0 if cold else p["min_ready_replicas"]
        if action in ("warmup", "start"):
            minimum = max(minimum, p["desired_replicas"])
        maximum = 0 if cold else p["max_replicas"]
        # Persist intent before the paid override; credential deletion is guarded by this record.
        with ctx.Session() as db:
            op = service.fenced(db, ctx.op_id, ctx.generation)
            op.handles = dict(
                op.handles or {},
                maintenance={
                    "warm_until": p.get("warm_until"),
                    "min_replicas": minimum,
                    "max_replicas": maximum,
                    "started_at": datetime.utcnow().isoformat(),
                    "identity": engine.config["control_identity"],
                    "cleanup_required": True,
                },
            )
            for resource in (
                db.query(ControlResource)
                .filter_by(operation_id=ctx.op_id)
                .with_for_update()
            ):
                resource.maintenance_operation_id = ctx.op_id
            db.commit()
        ctx.admit_effect("autoscaler")
        obj.update_autoscaler(
            min_containers=minimum,
            max_containers=maximum,
            buffer_containers=0,
            scaledown_window=p["idle_timeout_seconds"],
        )
        ctx.handles(
            {
                "policy_applied": {
                    "generation": ctx.generation,
                    "profile_revision": plan["profile_revision"],
                    "min": minimum,
                    "max": maximum,
                    "idle_timeout_seconds": p["idle_timeout_seconds"],
                }
            }
        )
        if minimum:
            # The approved probe uses an actual inference in the deployed model process.
            ctx.event("warming", "Confirmando inferência e containers distintos")
            probes = []
            for _ in range(minimum):
                ctx.check()
                ctx.admit_effect("warm_probe")
                probes.append(obj.control_probe.spawn())
            found = {}
            for call in probes:
                result = call.get(timeout=120)
                if (
                    result.get("ready")
                    and result.get("fingerprint")
                    == engine.deployments[plan["feature"]]["fingerprint"]
                ):
                    found[result["container_id"]] = result
            if len(found) < minimum:
                raise RuntimeError("WARM_POOL_NOT_VERIFIED")
        else:
            found = {}
        # Public Function stats apply to a class method's shared service pool.
        stats = obj.transcribe.get_current_stats()
        count = pool_count(stats)
        if cold:
            ctx.event("cooling", "Aguardando liberação observada dos containers")
            end = time.monotonic() + min(180, p["idle_timeout_seconds"] + 120)
            while count and time.monotonic() < end:
                ctx.check()
                time.sleep(2)
                count = pool_count(obj.transcribe.get_current_stats())
            if count:
                raise RuntimeError("COOLDOWN_NOT_VERIFIED")
            if action == "drain_stop":
                with tempfile.TemporaryDirectory(prefix="modal-control-stop-") as home:
                    completed = stream_run(
                        [
                            sys.executable,
                            "-m",
                            "modal",
                            "app",
                            "stop",
                            "ingestify-whisper",
                            "--yes",
                        ],
                        env=adapter.subprocess_env(home),
                        cwd=".",
                        context=ctx,
                        timeout=120,
                    )
                if completed.returncode:
                    raise RuntimeError("DEPLOYMENT_STOP_FAILED")
                report = adapter.test_connection()
                if report.deployed:
                    raise RuntimeError("DEPLOYMENT_STOP_NOT_VERIFIED")
            with ctx.Session() as db:
                op = service.fenced(db, ctx.op_id, ctx.generation)
                maintenance = dict(
                    (op.handles or {}).get("maintenance") or {}, cleanup_required=False
                )
                op.handles = dict(op.handles or {}, maintenance=maintenance)
                from shared.engine_control.models import EngineOperation

                for previous in db.query(EngineOperation).filter_by(
                    engine_id=engine.id
                ):
                    old = (previous.handles or {}).get("maintenance")
                    if old and old.get("cleanup_required"):
                        previous.handles = dict(
                            previous.handles or {},
                            maintenance=dict(
                                old,
                                cleanup_required=False,
                                stopped_at=datetime.utcnow().isoformat(),
                            ),
                        )
                # Keep monetary exposure until provider reconciliation covers the interval.
                db.commit()
        return {
            "replicas_alive": count,
            "ready_replicas": len(found),
            "containers": list(found),
            "model_profile_id": p["model_profile_id"],
            "policy": {"min": minimum, "max": maximum},
            "cold": cold,
            "deployment_stopped": action == "drain_stop",
            "observed_at": datetime.utcnow().isoformat(),
        }

    def observe(self, engine, feature, profile, context):
        adapter = self._adapter(engine)
        obj = adapter._runner()
        meta = adapter.deployed_meta()
        return {
            "replicas_alive": pool_count(obj.transcribe.get_current_stats()),
            "fingerprint": meta.get("fingerprint"),
            "ready_replicas": 0,
            "protocol": meta.get("protocol"),
        }

    def reconcile(self, operation, observed):
        p = operation["plan"]
        expected = p.get("artifact_fingerprint") or operation["handles"].get(
            "deployment", {}
        ).get("fingerprint")
        # A metadata match alone never proves that a paid warm pool is ready.
        policy = operation["handles"].get("policy_applied") or {}
        ready = (
            p["type"] in ("deploy", "apply_profile", "restart")
            and not p["profile"]["min_ready_replicas"]
            and policy.get("profile_revision") == p["profile_revision"]
            and policy.get("max") == p["profile"]["max_replicas"]
            and policy.get("min") == 0
            and expected is not None
            and observed.get("fingerprint") == expected
        )
        return {"desired_applied": ready, "safe_to_unlock": ready}

    def cancel(self, operation, context):
        return {"cancel_requested": True, "requires_observation": True}

    def expire_maintenance(self, engine, op_id, session_factory):
        from shared.engine_control.models import EngineOperation

        adapter = self._adapter(engine)
        obj = adapter._runner()
        obj.update_autoscaler(
            min_containers=0, max_containers=0, buffer_containers=0, scaledown_window=2
        )
        count = pool_count(obj.transcribe.get_current_stats())
        if count:
            raise RuntimeError("BUDGET_STOP_UNCONFIRMED")
        with session_factory() as db:
            op = db.query(EngineOperation).filter_by(id=op_id).with_for_update().one()
            safe = op.state in ("succeeded", "failed", "cancelled")
            op.handles = dict(
                op.handles or {},
                maintenance=dict(
                    op.handles["maintenance"],
                    cleanup_required=not safe,
                    stopped_at=datetime.utcnow().isoformat(),
                ),
            )
            from shared.models import Engine

            e = db.query(Engine).filter_by(id=engine.id).with_for_update().one()
            if e.status == "active":
                e.status = "paused"
                e.version += 1
            for resource in db.query(ControlResource).filter_by(
                maintenance_operation_id=op_id
            ):
                resource.observed = {
                    "replicas_alive": 0,
                    "ready_replicas": 0,
                    "cold": True,
                }
                resource.observed_at = datetime.utcnow()
            db.commit()
