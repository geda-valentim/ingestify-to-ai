from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column,
    String,
    Integer,
    JSON,
    DateTime,
    Boolean,
    Text,
    Numeric,
    Date,
    UniqueConstraint,
)
from shared.database import Base


def uid():
    return str(uuid4())


class RuntimeProfile(Base):
    __tablename__ = "engine_runtime_profiles"
    id = Column(String(36), primary_key=True, default=uid)
    engine_id = Column(String(36), nullable=False, index=True)
    feature = Column(String(40), nullable=False)
    revision = Column(Integer, nullable=False)
    profile = Column(JSON, nullable=False)
    source_profile_revision_id = Column(String(36), index=True)
    source_hash = Column(String(64))
    applied_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "engine_id", "feature", "revision", name="uq_runtime_revision"
        ),
    )


class ControlResource(Base):
    __tablename__ = "engine_control_resources"
    key = Column(String(200), primary_key=True)
    owner_engine_id = Column(String(36), nullable=False)
    operation_id = Column(String(36), index=True)
    gate_closed = Column(Boolean, nullable=False, default=False)
    maintenance_operation_id = Column(String(36), index=True)
    applied = Column(JSON, nullable=False, default=dict)
    observed = Column(JSON, nullable=False, default=dict)
    observed_at = Column(DateTime)


class OperationPlan(Base):
    __tablename__ = "engine_operation_plans"
    id = Column(String(36), primary_key=True, default=uid)
    engine_id = Column(String(36), nullable=False, index=True)
    actor_id = Column(String(36), nullable=False)
    engine_version = Column(Integer, nullable=False)
    profile_id = Column(String(36))
    body = Column(JSON, nullable=False)
    hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EngineOperation(Base):
    __tablename__ = "engine_operations"
    id = Column(String(36), primary_key=True, default=uid)
    engine_id = Column(String(36), nullable=False, index=True)
    actor_id = Column(String(36), nullable=False)
    plan_id = Column(String(36), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    state = Column(String(24), nullable=False, default="queued", index=True)
    stage = Column(String(40), nullable=False, default="queued")
    generation = Column(Integer, nullable=False, default=0)
    holder = Column(String(128))
    lease_until = Column(DateTime)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    cancel_requested_by = Column(String(36))
    recovery_requested_by = Column(String(36))
    effect_started = Column(Boolean, nullable=False, default=False)
    handles = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=False, default=dict)
    error = Column(JSON)
    seq = Column(Integer, nullable=False, default=0)
    log_bytes = Column(Integer, nullable=False, default=0)
    deadline = Column(DateTime, nullable=False)
    period_start = Column(Date)
    reserved_usd = Column(Numeric(14, 6), nullable=False, default=0)
    actual_usd = Column(Numeric(14, 6))
    cost_confirmed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "idempotency_key", name="uq_operation_idempotency"
        ),
    )


class OperationEvent(Base):
    __tablename__ = "engine_operation_events"
    operation_id = Column(String(36), primary_key=True)
    seq = Column(Integer, primary_key=True)
    type = Column(String(40), nullable=False)
    stage = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OperationOutbox(Base):
    __tablename__ = "engine_operation_outbox"
    operation_id = Column(String(36), primary_key=True)
    published_at = Column(DateTime)
    attempts = Column(Integer, nullable=False, default=0)


class ControlAdmission(Base):
    __tablename__ = "engine_control_admissions"
    id = Column(String(36), primary_key=True, default=uid)
    resource_key = Column(String(200), nullable=False, index=True)
    holder = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    released_at = Column(DateTime)


class ControlHost(Base):
    __tablename__ = "engine_control_hosts"
    id = Column(String(64), primary_key=True)
    inventory = Column(JSON, nullable=False, default=dict)
    seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
