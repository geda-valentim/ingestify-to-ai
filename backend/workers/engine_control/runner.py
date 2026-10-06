import threading
import time
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import update
from shared.config import get_settings
from shared.database import SessionLocal
from shared.engine_control import service, registry
from shared.engine_control.contracts import utc_deadline
from shared.engine_control.models import (
    EngineOperation,
    OperationPlan,
    OperationOutbox,
    ControlResource,
    ControlAdmission,
)
from shared.models import Engine, EngineUsage


class Cancelled(Exception):
    pass


class Context:
    def __init__(self, op_id, generation, session_factory=SessionLocal):
        self.op_id, self.generation, self.Session = op_id, generation, session_factory
        self.stop = threading.Event()
        self.lost = False
        self.last_log = 0.0
        self.omitted_logs = 0
        self.thread = threading.Thread(target=self._renew, daemon=True)
        self.thread.start()

    def _renew(self):
        while not self.stop.wait(5):
            try:
                with self.Session() as db:
                    service.heartbeat(db, self.op_id, self.generation)
            except Exception:
                self.lost = True
                return

    def check(self):
        if self.lost:
            raise service.ControlError("LEASE_LOST")
        with self.Session() as db:
            op = service.fenced(db, self.op_id, self.generation)
            if op.cancel_requested:
                raise Cancelled()
            if op.deadline <= service.now():
                raise TimeoutError("OPERATION_DEADLINE")
            maintenance = (op.handles or {}).get("maintenance") or {}
            until = maintenance.get("warm_until")
            if (
                maintenance.get("min_replicas")
                and until
                and utc_deadline(until) <= service.now()
            ):
                raise TimeoutError("WARM_DEADLINE")

    def event(self, stage, message=None, kind="stage.changed", effect=False):
        self.check()
        with self.Session() as db:
            service.event(
                db,
                self.op_id,
                self.generation,
                stage,
                {"message": message or stage},
                kind,
                effect,
            )

    def log(self, message):
        stamp = time.monotonic()
        if stamp - self.last_log < 0.1:
            self.omitted_logs += 1
            return
        if self.omitted_logs:
            message = f"[{self.omitted_logs} linhas agregadas] " + message
            self.omitted_logs = 0
        self.last_log = stamp
        self.event("applying", message, "log")

    def handles(self, value):
        with self.Session() as db:
            op = service.fenced(db, self.op_id, self.generation)
            op.handles = service.clean(dict(op.handles or {}, **value))
            db.commit()

    def assign_host(self, host_id):
        self.handles({"host_id": host_id, "assigned": True})
        self.event("waiting_host", "Aguardando o agente do host")
        while True:
            self.check()
            with self.Session() as db:
                op = db.get(EngineOperation, self.op_id)
                response = (op.handles or {}).get("host_result")
                if response:
                    if not response.get("ok"):
                        raise RuntimeError(response.get("code", "HOST_APPLY_FAILED"))
                    return response["observed"]
            time.sleep(1)

    def host_observation(self, host_id):
        return {}

    def drain(self, plan):
        self.event(
            "draining", "Bloqueando novas admissões e aguardando trabalho em voo"
        )
        with self.Session() as db:
            e = service.locked_engine(db, plan["engine_id"])
            service.fenced(db, self.op_id, self.generation)
            rows = (
                db.query(ControlResource)
                .filter_by(operation_id=self.op_id)
                .order_by(ControlResource.key)
                .with_for_update()
                .all()
            )
            for r in rows:
                r.gate_closed = True
            # Reserved work has not started. Reuse the ledger's release/requeue path outside this txn.
            pending = [
                u.id
                for u in db.query(EngineUsage).filter_by(
                    engine_id=e.id, status="reserved"
                )
            ]
            db.commit()
        from shared.engines import ledger

        for usage_id in pending:
            ledger.release(
                usage_id, error_code="ENGINE_MAINTENANCE", session_factory=self.Session
            )
        end = time.monotonic() + plan["drain_timeout_seconds"]
        while time.monotonic() < end:
            self.check()
            with self.Session() as db:
                tickets = (
                    db.query(ControlAdmission)
                    .filter(
                        ControlAdmission.resource_key.in_(plan["resources"]),
                        ControlAdmission.released_at.is_(None),
                    )
                    .count()
                )
                usages = (
                    db.query(EngineUsage)
                    .filter(
                        EngineUsage.engine_id == plan["engine_id"],
                        EngineUsage.status.in_(("spawning", "running")),
                    )
                    .count()
                )
                if not tickets and not usages:
                    return
            time.sleep(0.5)
        raise TimeoutError("DRAIN_TIMEOUT")

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)


def run(op_id, session_factory=SessionLocal):
    with session_factory() as db:
        generation = service.claim(db, op_id, "control:" + str(uuid4()))
        if generation is None:
            return
        op = db.get(EngineOperation, op_id)
        plan = dict(db.get(OperationPlan, op.plan_id).body)
        recovering = (op.handles or {}).get("recovery_mode", False)
        old_handles = dict(op.handles or {})
    ctx = Context(op_id, generation, session_factory)
    try:
        ctx.event("validating", "Verificando plano e dependências")
        with session_factory() as db:
            e = service.locked_engine(db, plan["engine_id"])
            p = db.get(OperationPlan, op.plan_id)
            if e.version != p.engine_version:
                raise service.ControlError("PLAN_STALE")
        if plan["drain"] and not recovering:
            ctx.drain(plan)
        driver = registry.create(plan["adapter_type"], plan["adapter_version"])
        if recovering:
            with session_factory() as db:
                e = db.get(Engine, plan["engine_id"])
                db.expunge(e)
            observation = driver.observe(e, plan["feature"], plan["profile"], ctx)
            proof = driver.reconcile(dict(plan=plan, handles=old_handles), observation)
            if not proof.get("desired_applied") or not proof.get("safe_to_unlock"):
                raise RuntimeError("RECOVERY_STATE_UNCONFIRMED")
            result = observation
        else:
            result = driver.apply(plan, ctx)
        ctx.event("verifying", "Publicando apenas o estado verificado")
        with session_factory() as db:
            service.publish_applied(db, op_id, generation, result)
        with session_factory() as db:
            service.finish(db, op_id, generation, "succeeded", result, safe=True)
    except Exception as exc:
        try:
            with session_factory() as db:
                current = db.get(EngineOperation, op_id)
                effect = current.effect_started
                state = (
                    "needs_attention"
                    if effect
                    else "cancelled" if isinstance(exc, Cancelled) else "failed"
                )
                service.finish(
                    db,
                    op_id,
                    generation,
                    state,
                    error={"code": str(exc) or "CANCELLED", "message": str(exc)},
                    safe=not effect,
                )
        except service.ControlError:
            pass  # Lost executors cannot publish terminal state or unlock anything.
    finally:
        ctx.close()
        with session_factory() as db:
            current = (
                db.query(EngineOperation)
                .filter_by(id=op_id, generation=generation)
                .with_for_update()
                .first()
            )
            if current:
                current.handles = dict(current.handles or {}, executor_exited=True)
                db.commit()


def sweep(celery, session_factory=SessionLocal):
    # Durable outbox. Re-publication is safe: claim does not repeat external effects.
    with session_factory() as db:
        ids = [
            x.operation_id
            for x in db.query(OperationOutbox)
            .join(EngineOperation, EngineOperation.id == OperationOutbox.operation_id)
            .filter(
                ~EngineOperation.state.in_(service.TERMINAL),
                (OperationOutbox.published_at.is_(None))
                | (
                    OperationOutbox.published_at < service.now() - timedelta(seconds=30)
                ),
            )
            .limit(100)
        ]
    for op_id in ids:
        celery.send_task(
            "workers.engine_control.tasks.execute",
            args=[op_id],
            queue=get_settings().engine_control_queue,
        )
        with session_factory() as db:
            row = db.get(OperationOutbox, op_id)
            row.published_at = service.now()
            row.attempts += 1
            db.commit()
