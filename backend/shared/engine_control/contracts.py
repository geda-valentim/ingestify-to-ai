from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Protocol
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from shared.engines.capacity import Binding

ACTIONS = (
    "test",
    "reconcile",
    "deploy",
    "start",
    "drain_stop",
    "restart",
    "scale",
    "warmup",
    "cooldown",
    "apply_profile",
    "benchmark",
)
TERMINAL = {"succeeded", "failed", "cancelled", "needs_attention"}


def utc_deadline(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("A warm deadline requires a timezone")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ControlBinding(Binding):
    model_config = ConfigDict(extra="forbid")


class RuntimeSettings(Closed):
    adapter_version: int = Field(1, ge=1, le=1)
    schema_version: int = Field(1, ge=1, le=1)
    binding: ControlBinding
    model_profile_id: str
    desired_replicas: int = Field(1, ge=0, le=100)
    max_replicas: int = Field(1, ge=0, le=100)
    min_ready_replicas: int = Field(0, ge=0, le=100)
    idle_timeout_seconds: int = Field(60, ge=2, le=3600)
    memory_mb: int | None = Field(None, ge=256, le=262144)
    warmup_mode: Literal["on_start", "manual"] = "on_start"
    warm_until: AwareDatetime | None = None
    provider_settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounds(self):
        if max(self.desired_replicas, self.min_ready_replicas) > self.max_replicas:
            raise ValueError("Replica minima/desire cannot exceed maximum")
        if self.binding.workers != self.max_replicas:
            raise ValueError(
                "binding.workers must equal max_replicas (execution capacity)"
            )
        return self


class PlanRequest(Closed):
    type: str
    feature: str = "transcription"
    profile_revision: int | None = Field(None, ge=1)
    engine_version: int = Field(ge=0)
    drain_timeout_seconds: int = Field(900, ge=1, le=1800)
    max_usd: Decimal = Field(Decimal("0"), ge=0, le=1000)

    @model_validator(mode="after")
    def action(self):
        if self.type not in ACTIONS:
            raise ValueError("Unknown operation type")
        return self


class EngineControlAdapter(Protocol):
    def describe(self) -> dict: ...
    def resource_keys(self, engine, feature, profile) -> list[str]: ...
    def validate(self, engine, feature, profile, db) -> dict: ...
    def plan(self, engine, request, profile, db) -> dict: ...
    def apply(self, plan, context) -> dict: ...
    def observe(self, engine, feature, profile, context) -> dict: ...
    def reconcile(self, operation, observed) -> dict: ...
    def cancel(self, operation, context) -> dict: ...
