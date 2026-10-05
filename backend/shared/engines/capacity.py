"""
How much work an engine may run at once, and whether it fits in GPU memory.

A binding says how one feature runs on one engine: which GPU, how many workers
(Modal containers, or local replicas) and how many executions each runs at once.
Capacity = workers x executions_per_worker: the dispatcher never has more items
in flight on that (engine, feature). Validation refuses a configuration that does
not fit in VRAM - summed over every feature sharing a physical local GPU - and
says which term breaks it (spec 0003, section 4.6).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator

from shared.engines.features import FEATURES, default_vram_gb, get_feature
from shared.engines.gpus import DEFAULT_ACCOUNT_MAX_GPUS, DEFAULT_VRAM_RESERVE_GB, MODAL_GPUS

# Executions per worker allowed per adapter until a remote gate proves more is safe
# (spec 0003, 4.6.3): Modal 1 until T4/T8 pass; a local GPU process holds one model,
# so more executions means more replicas, not concurrency
MODAL_MAX_E = 1
LOCAL_GPU_MAX_E = 1

ADAPTER_FEATURES = {
    "local": set(FEATURES),
    "modal": {"transcription"},
}


class CapacityError(ValueError):
    """A configuration that cannot run; `lines` explains the VRAM arithmetic when that is the cause"""

    def __init__(self, message: str, lines: Optional[List[str]] = None):
        super().__init__(message)
        self.lines = lines or []


class Binding(BaseModel):
    gpu_type: Optional[str] = None  # remote: one of the adapter's gpu_options
    gpu_ref: Optional[str] = None  # local: a declared physical GPU; None = runs on CPU
    workers: int = Field(ge=0, le=1000)
    executions_per_worker: int = Field(1, ge=1, le=64)
    cpu: Optional[float] = Field(None, gt=0, le=64)
    vram_override_gb: Optional[float] = Field(None, gt=0, le=200)

    @model_validator(mode="after")
    def _one_gpu_field(self):
        if self.gpu_type and self.gpu_ref:
            raise ValueError("Set gpu_type (remote) or gpu_ref (local), not both")
        return self

    @property
    def capacity(self) -> int:
        return self.workers * self.executions_per_worker


class LocalGpu(BaseModel):
    ref: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = ""
    uuid: Optional[str] = None
    vram_gb: float = Field(gt=0, le=1000)
    vram_reserve_gb: float = Field(DEFAULT_VRAM_RESERVE_GB, ge=0)


@dataclass
class VramUse:
    """Budget of one GPU (local: a physical card; remote: one worker of a binding)"""
    gpu: str
    vram_gb: float
    reserve_gb: float
    terms: List[str] = field(default_factory=list)
    used_gb: float = 0.0

    @property
    def budgeted_gb(self) -> float:
        return round(self.used_gb + self.reserve_gb, 2)

    @property
    def fits(self) -> bool:
        return self.budgeted_gb <= self.vram_gb + 1e-9

    def explain(self) -> List[str]:
        verdict = "fits" if self.fits else "does NOT fit"
        return [f"{self.gpu}: " + " + ".join(self.terms + [f"reserve {self.reserve_gb:g}"])
                + f" = {self.budgeted_gb:g} GB of {self.vram_gb:g} GB - {verdict}"]


def bindings(config: dict) -> Dict[str, Binding]:
    return {feature: Binding(**raw) for feature, raw in (config.get("features") or {}).items()}


def footprint_gb(feature: str, binding: Binding, vision_model_id: Optional[str] = None) -> float:
    return binding.vram_override_gb or default_vram_gb(feature, vision_model_id)


def max_executions_per_worker(adapter_type: str, binding: Binding) -> Optional[int]:
    if adapter_type == "modal":
        return MODAL_MAX_E
    if adapter_type == "local" and binding.gpu_ref:
        return LOCAL_GPU_MAX_E
    return None  # local CPU work: Celery concurrency as configured


def validate_engine_config(adapter_type: str, config: dict, vision_model_id: Optional[str] = None) -> List[VramUse]:
    """
    Raise CapacityError if the engine's bindings cannot run; otherwise return the
    VRAM budget of each GPU involved (for the admin view).
    """
    try:
        by_feature = bindings(config)
        gpus = [LocalGpu(**raw) for raw in (config.get("gpus") or [])]
    except ValidationError as e:
        raise CapacityError(f"Invalid engine configuration: {e.errors()[0]['msg']}") from None

    supported = ADAPTER_FEATURES.get(adapter_type)
    if supported is None:
        raise CapacityError(f"Unknown adapter type {adapter_type!r}")
    for feature, binding in by_feature.items():
        get_feature(feature)
        if feature not in supported:
            raise CapacityError(f"The {adapter_type} adapter cannot run {feature}")
        limit = max_executions_per_worker(adapter_type, binding)
        if limit is not None and binding.executions_per_worker > limit:
            hint = " - add workers (replicas) instead" if adapter_type == "local" else \
                " until concurrent inputs are verified safe (spec 0003 gates T4/T8)"
            raise CapacityError(
                f"{feature}: executions_per_worker={binding.executions_per_worker} exceeds {limit}{hint}"
            )

    if adapter_type == "local":
        return _validate_local(by_feature, gpus, vision_model_id)
    return _validate_modal(config, by_feature, vision_model_id)


def _validate_local(by_feature: Dict[str, Binding], gpus: List[LocalGpu], vision_model_id) -> List[VramUse]:
    declared = {g.ref: g for g in gpus}
    uses = {g.ref: VramUse(f"GPU {g.ref} ({g.name or 'declared'})", g.vram_gb, g.vram_reserve_gb) for g in gpus}
    for feature, binding in sorted(by_feature.items()):
        if not binding.gpu_ref:
            continue  # CPU binding
        if binding.gpu_type:
            raise CapacityError(f"{feature}: a local binding names a declared GPU with gpu_ref, not gpu_type")
        if binding.gpu_ref not in declared:
            raise CapacityError(f"{feature}: GPU {binding.gpu_ref!r} is not declared on the local engine")
        each = footprint_gb(feature, binding, vision_model_id)
        use = uses[binding.gpu_ref]
        use.used_gb += binding.workers * binding.executions_per_worker * each
        use.terms.append(f"{feature} {binding.workers}x{binding.executions_per_worker}x{each:g}")
    broken = [u for u in uses.values() if not u.fits]
    if broken:
        lines = [line for u in broken for line in u.explain()]
        raise CapacityError("The local bindings do not fit in GPU memory", lines)
    return list(uses.values())


def _validate_modal(config: dict, by_feature: Dict[str, Binding], vision_model_id) -> List[VramUse]:
    uses = []
    for feature, binding in sorted(by_feature.items()):
        if binding.gpu_ref:
            raise CapacityError(f"{feature}: a remote binding picks a gpu_type, not a gpu_ref")
        option = MODAL_GPUS.get(binding.gpu_type or "")
        if option is None:
            raise CapacityError(f"{feature}: gpu_type must be one of {', '.join(MODAL_GPUS)}")
        each = footprint_gb(feature, binding, vision_model_id)
        use = VramUse(f"{feature} on {option.gpu_type}", option.vram_gb, DEFAULT_VRAM_RESERVE_GB,
                      [f"{binding.executions_per_worker}x{each:g}"], binding.executions_per_worker * each)
        if not use.fits:
            raise CapacityError(f"{feature} does not fit on one {option.gpu_type}", use.explain())
        uses.append(use)

    max_gpus = int(config.get("account_max_gpus") or DEFAULT_ACCOUNT_MAX_GPUS)
    total = sum(b.workers for b in by_feature.values())
    if total > max_gpus:
        raise CapacityError(
            f"The account's bindings ask for {total} GPUs at once, above account_max_gpus={max_gpus}"
        )
    return uses


def deploy_state(adapter_type: str, deployments: dict, feature: str, binding: Binding) -> str:
    """
    local: always runs what is configured. modal: the deployed app must match the
    binding (GPU, workers, executions live in the function's decorator), so any
    change waits for a deploy and the binding takes no new items meanwhile.
    """
    if adapter_type == "local":
        return "local"
    deployed = (deployments or {}).get(feature)
    if not deployed:
        return "not_deployed"
    return "deployed" if deployed.get("binding") == binding.model_dump(exclude_none=True) else "needs_redeploy"
