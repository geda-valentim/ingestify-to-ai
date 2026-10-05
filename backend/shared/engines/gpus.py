"""
GPUs a remote provider offers, with memory and price.

Prices are what Modal published when this table was written (`PRICES_AS_OF`) and
must be verified before relying on them; an engine's config can override any of
them (`prices`). Local GPUs are not listed here: they are detected by the workers'
heartbeats and declared on the local engine.
"""

from dataclasses import dataclass
from typing import Dict

PRICES_AS_OF = "2026-10-04"
PRICES_VERIFIED = False

# Per account: concurrent GPUs on Modal's Starter plan (verify for the account's plan)
DEFAULT_ACCOUNT_MAX_GPUS = 10
DEFAULT_VRAM_RESERVE_GB = 1.0


@dataclass(frozen=True)
class GpuOption:
    gpu_type: str
    vram_gb: float
    usd_per_second: float


MODAL_GPUS: Dict[str, GpuOption] = {
    g.gpu_type: g
    for g in (
        GpuOption("T4", 16, 0.000164),
        GpuOption("L4", 24, 0.000222),
        GpuOption("A10G", 24, 0.000306),
        GpuOption("L40S", 48, 0.000542),
        GpuOption("A100-40GB", 40, 0.000583),
        GpuOption("A100-80GB", 80, 0.000694),
        GpuOption("H100", 80, 0.001097),
    )
}
