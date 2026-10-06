"""SQL authorities and immutable execution templates (spec 0009)."""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column,
    String,
    Integer,
    JSON,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from shared.database import Base


def uid():
    return str(uuid4())


class ExecutionProfile(Base):
    __tablename__ = "execution_profiles"
    id = Column(String(36), primary_key=True, default=uid)
    name = Column(String(100), nullable=False)
    description = Column(String(1000), nullable=False, default="")
    adapter_type = Column(String(64), nullable=False)
    feature = Column(String(64), nullable=False)
    environment = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    version = Column(Integer, nullable=False, default=0)
    latest_published_revision_id = Column(String(36))
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    origin_grant_id = Column(String(36))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ExecutionRevision(Base):
    __tablename__ = "execution_profile_revisions"
    id = Column(String(36), primary_key=True, default=uid)
    profile_id = Column(
        String(36), ForeignKey("execution_profiles.id"), nullable=False, index=True
    )
    revision = Column(Integer, nullable=False)
    settings = Column(JSON, nullable=False)
    warm_for_seconds = Column(Integer)
    model_fingerprint = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)
    published_at = Column(DateTime)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("profile_id", "revision", name="uq_execution_revision"),
    )


class AccessPolicy(Base):
    __tablename__ = "access_policies"
    id = Column(String(36), primary_key=True, default=uid)
    name = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False, default=0)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)


class PolicyRevision(Base):
    __tablename__ = "access_policy_revisions"
    id = Column(String(36), primary_key=True, default=uid)
    policy_id = Column(
        String(36), ForeignKey("access_policies.id"), nullable=False, index=True
    )
    revision = Column(Integer, nullable=False)
    constraints = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("policy_id", "revision", name="uq_access_policy_revision"),
    )


class RoleGrant(Base):
    __tablename__ = "access_role_grants"
    id = Column(String(36), primary_key=True, default=uid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(64), nullable=False)
    permissions = Column(JSON, nullable=False)
    policy_revision_id = Column(
        String(36), ForeignKey("access_policy_revisions.id"), nullable=False
    )
    delegation = Column(JSON)
    parent_id = Column(String(36), ForeignKey("access_role_grants.id"))
    granted_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuthorizationEpoch(Base):
    __tablename__ = "access_authorization_epoch"
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False, default=0)


class EngineAttributes(Base):
    __tablename__ = "access_engine_attributes"
    engine_id = Column(String(36), ForeignKey("engines.id"), primary_key=True)
    environment = Column(String(20), nullable=False)
    version = Column(Integer, nullable=False, default=0)


class ResourceScope(Base):
    __tablename__ = "access_resource_scopes"
    key = Column(String(200), primary_key=True)
    consumers = Column(JSON, nullable=False)
    qualified = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=0)


class EffectAdmission(Base):
    __tablename__ = "access_effect_admissions"
    id = Column(String(36), primary_key=True, default=uid)
    operation_id = Column(String(36), nullable=False, index=True)
    generation = Column(Integer, nullable=False)
    step = Column(String(100), nullable=False)
    actor_id = Column(String(80), nullable=False)
    executor = Column(String(100), nullable=False)
    epoch = Column(Integer, nullable=False)
    action = Column(String(64), nullable=False, default="effect")
    targets = Column(JSON, nullable=False, default=list)
    decision = Column(JSON, nullable=False, default=dict)
    valid_until = Column(DateTime)
    state = Column(String(20), nullable=False, default="admitted")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("operation_id", "generation", "step", name="uq_effect_step"),
    )


class LegacyRequest(Base):
    __tablename__ = "access_legacy_requests"
    id = Column(String(36), primary_key=True, default=uid)
    actor_id = Column(String(36), nullable=False)
    action = Column(String(40), nullable=False)
    engine_ids = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    epoch = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ServicePrincipal(Base):
    __tablename__ = "access_service_principals"
    id = Column(String(36), primary_key=True)
    purpose = Column(String(40), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
