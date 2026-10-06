from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, AwareDatetime, StringConstraints
from shared.engine_control.contracts import Closed, RuntimeSettings

Environment = Literal["development", "staging", "production"]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class Constraints(Closed):
    engine_ids: list[str] = Field(default_factory=list, max_length=200)
    profile_ids: list[str] | None = Field(None, max_length=200)
    adapters: list[str] = Field(default_factory=list, max_length=100)
    features: list[str] = Field(default_factory=list, max_length=100)
    environments: list[Environment] = Field(default_factory=list)
    host_ids: list[str] | None = Field(None, max_length=100)
    gpu_uuids: list[str] | None = Field(None, max_length=100)
    model_ids: list[str] | None = Field(None, max_length=100)
    max_replicas: int = Field(0, ge=0, le=100)
    max_concurrency: int = Field(1, ge=1, le=100)
    max_cpu: float = Field(1, gt=0, le=256)
    max_memory_mb: int = Field(256, ge=256, le=262144)
    max_warm_seconds: int = Field(0, ge=0, le=86400)
    max_usd: Decimal = Field(Decimal("0"), ge=0, le=1000)


class Template(Closed):
    settings: RuntimeSettings
    warm_for_seconds: int | None = Field(None, ge=1, le=86400)


class ProfileCreate(Template):
    name: Name
    description: str = Field("", max_length=1000)
    adapter_type: str
    feature: str
    environment: Environment = "development"


class RevisionCreate(Template):
    version: int = Field(ge=0)


class MetadataUpdate(Closed):
    version: int = Field(ge=0)
    name: Name
    description: str = Field("", max_length=1000)


class Publish(Closed):
    version: int = Field(ge=0)
    revision_id: str


class Version(Closed):
    version: int = Field(ge=0)


class Bind(Closed):
    version: int = Field(ge=0)
    feature: str
    revision_id: str


class PolicyCreate(Closed):
    name: Name
    constraints: Constraints


class PolicyUpdate(Closed):
    version: int = Field(ge=0)
    constraints: Constraints


class Delegation(Closed):
    permissions: list[str] = Field(max_length=100)
    constraints: Constraints
    max_grant_seconds: int = Field(3600, ge=60, le=31536000)


class GrantCreate(Closed):
    user_id: str
    role: str
    policy_revision_id: str
    permissions: list[str] | None = Field(None, max_length=100)
    expires_at: AwareDatetime
    delegation: Delegation | None = None


class Consumer(Closed):
    engine_id: str
    feature: str


class ScopeUpdate(Closed):
    key: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=0)
    consumers: list[Consumer] = Field(min_length=1, max_length=100)
    qualified: bool = False


class AttributesUpdate(Closed):
    version: int = Field(ge=0)
    environment: Environment


class PrincipalCreate(Closed):
    id: str = Field(pattern=r"^installation:[a-z0-9_-]{1,23}$", max_length=36)


class PrincipalState(Closed):
    version: int = Field(ge=0)
    active: bool


class SubjectState(Closed):
    expected_is_active: bool
    expected_is_admin: bool
    is_active: bool
    is_admin: bool
