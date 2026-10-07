"""
IAM bindings (spec 0014 §4.8).

A table of its own, never `access_role_grants`: the 0009 grants drive
`active_grant`, `navigation` and `access_session`, and a platform binding must not
open the engine routes (0013 §4.2).
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

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

    __table_args__ = (
        Index("ix_iam_bindings_subject", "subject_type", "subject_id", "revoked_at"),
        Index("ix_iam_bindings_scope", "scope_type", "scope_id"),
    )
