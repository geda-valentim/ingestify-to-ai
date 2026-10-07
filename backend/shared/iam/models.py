"""
IAM bindings (spec 0014 §4.8; engine columns since spec 0018 §4.1).

Two role families share this table and never see each other (0018 §4.3):

- `platform` (keys of `catalog.ROLES`): decided by `shared.iam.decide`; the four
  engine columns below are always NULL.
- `engines` (keys of `catalog.ENGINE_ROLES`, the six 0009 roles): migrated from
  `access_role_grants` with the same ids (0018 §4.2.2). `permissions` is always
  materialized, `condition_ref` names the ABAC policy revision, and `delegation` /
  `parent_id` carry the 0009 delegation envelope and parent grant.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String

from shared.database import Base

SUBJECT_TYPES = ("user", "service_principal")  # `group` arrives with 0017
SCOPE_TYPES = ("platform",)  # other scopes arrive with 0016/0017


def uid():
    return str(uuid4())


class IamBinding(Base):
    __tablename__ = "iam_bindings"

    id = Column(String(36), primary_key=True, default=uid)
    subject_type = Column(String(32), nullable=False)
    # Logical FK (users.id or access_service_principals.id), validated on write.
    subject_id = Column(String(80), nullable=False)
    # Key of a managed role in shared/iam/catalog.py.
    role = Column(String(64), nullable=False)
    scope_type = Column(String(32), nullable=False, default="platform")
    scope_id = Column(String(80))
    granted_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    # Naive UTC, like every DateTime here. At most 365 days for scope `platform`.
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)
    revoked_by = Column(String(36), ForeignKey("users.id"))
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # -- engines family only (spec 0018 §4.1); NULL for platform roles -----------
    # Materialized snapshot, never NULL for an engines role: a role gaining an
    # action does not widen existing bindings.
    permissions = Column(JSON)
    # The 0009 ABAC condition: an `access_policy_revisions` id.
    condition_ref = Column(
        String(36),
        ForeignKey("access_policy_revisions.id", name="fk_iam_bindings_condition_ref"),
    )
    # The 0009 delegation envelope (`access_admin` only).
    delegation = Column(JSON)
    # The `access_admin` binding that authorized this one by delegation.
    parent_id = Column(String(36), ForeignKey("iam_bindings.id", name="fk_iam_bindings_parent"))

    __table_args__ = (
        Index("ix_iam_bindings_subject", "subject_type", "subject_id", "revoked_at"),
        Index("ix_iam_bindings_scope", "scope_type", "scope_id"),
        # Lock order of 0018 §4.3: BINDING_EXISTS locks only platform-role rows.
        Index("ix_iam_bindings_subject_role", "subject_type", "subject_id", "role"),
    )
