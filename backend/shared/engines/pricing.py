"""
What a remote attempt costs and how its function is sized (spec 0003, 4.6.6 and 4.7).

    rate   = P_gpu + cpu x P_cpu + memory_GiB x P_mem          (US$ per second of container)
    hold   = (D / speed + 15 + P_cold x cold_s) x rate x (1 + margin)
             reserved at placement; with E = 1 it is also the attempt's ceiling:
             deadline_at = spawned_at + reserved / rate
    actual = max(reported_seconds, measured_seconds) x rate     (settle, E = 1)

The decorator values (cpu, memory, timeout, scaledown_window, max_containers)
live in the deployed Modal function, so they are part of the deploy fingerprint:
changing any of them needs a redeploy. Prices are the table in gpus.py
(`prices_as_of`, to verify - gate T5) unless the engine's config overrides them
(`prices: {gpu_usd_per_s, cpu_usd_per_core_s, mem_usd_per_gib_s}`).

Pure arithmetic on Decimal: no database, no provider, importable anywhere.
"""

import math
from decimal import ROUND_CEILING, Decimal
from typing import Dict, Optional

from shared.engines.gpus import MODAL_GPUS, PRICES_AS_OF

# Modal's CPU and memory prices (per physical core and per GiB, per second);
# together with cpu=2 and 6 GiB about US$ 0.144/h (spec 0003, Appendix G)
MODAL_CPU_USD_PER_CORE_S = Decimal("0.0000131")
MODAL_MEM_USD_PER_GIB_S = Decimal("0.00000222")

# Defaults of an engine's config (Appendix A); all overridable per engine
DEFAULT_MAX_MEDIA_SECONDS = 4 * 3600  # remote admission limit: longer items stay local
DEFAULT_SPEED = 10.0  # x real time per item, until measured (benchmark or 50 ledger rows)
DEFAULT_MIN_SPEED = 3.0  # worst case for the function timeout
DEFAULT_COLD_START_SECONDS = 30.0
DEFAULT_SCALEDOWN_WINDOW = 60
DEFAULT_MARGIN = Decimal("0.2")
FIXED_OVERHEAD_SECONDS = 15  # upload, model warm path, result download
TIMEOUT_SLACK_SECONDS = 300
MICRO = Decimal("0.000001")


def _dec(value) -> Decimal:
    return Decimal(str(value))


def round_up(value: Decimal) -> Decimal:
    """Money is reserved rounded up to the micro-dollar"""
    return value.quantize(MICRO, rounding=ROUND_CEILING)


def cpu_for(binding) -> float:
    """cpu of the decorator: the binding's, or 1 + E (spec 0003, R20)"""
    return float(binding.cpu) if binding.cpu else float(1 + binding.executions_per_worker)


def memory_gib(config: dict, binding) -> float:
    """4 + E x (0.5 + 0.45 x max_h) GiB, max_h the longest admissible media in hours"""
    max_h = float(config.get("max_media_seconds") or DEFAULT_MAX_MEDIA_SECONDS) / 3600
    minimum=round(4 + binding.executions_per_worker * (0.5 + 0.45 * max_h), 2)
    declared=config.get('control_memory_mb') if config.get('control_fingerprint_version')==2 else None
    if declared is not None:
        if float(declared)/1024<minimum:
            raise ValueError(f'Memory must be at least {int(math.ceil(minimum*1024))} MiB for this binding')
        return float(declared)/1024
    return minimum


def function_timeout(config: dict) -> int:
    """The Modal function's own timeout: the second barrier after deadline_at"""
    max_media = float(config.get("max_media_seconds") or DEFAULT_MAX_MEDIA_SECONDS)
    min_speed = float(config.get("min_speed") or DEFAULT_MIN_SPEED)
    return int(math.ceil(max_media / min_speed)) + TIMEOUT_SLACK_SECONDS


def modal_decorator(config: dict, binding) -> Dict[str, object]:
    """Everything the deployed function's decorator holds; part of the fingerprint"""
    return {
        "gpu": binding.gpu_type,
        "cpu": cpu_for(binding),
        "memory_mib": int(math.ceil(memory_gib(config, binding) * 1024)),
        "timeout": function_timeout(config),
        "scaledown_window": int(config.get("scaledown_window") or DEFAULT_SCALEDOWN_WINDOW),
        "max_containers": binding.workers,
        "max_inputs": binding.executions_per_worker,
        "min_containers": 0,
    }


def prices(config: dict, binding) -> Dict[str, object]:
    """The price snapshot a reservation records (`price_snapshot`)"""
    override = config.get("prices") or {}
    option = MODAL_GPUS.get(binding.gpu_type or "")
    gpu = override.get("gpu_usd_per_s")  # the price of the binding's GPU, when it differs from the table
    return {
        "gpu_type": binding.gpu_type,
        "gpu_usd_per_s": str(_dec(gpu if gpu is not None else (option.usd_per_second if option else 0))),
        "cpu_usd_per_core_s": str(_dec(override.get("cpu_usd_per_core_s", MODAL_CPU_USD_PER_CORE_S))),
        "mem_usd_per_gib_s": str(_dec(override.get("mem_usd_per_gib_s", MODAL_MEM_USD_PER_GIB_S))),
        "cpu": cpu_for(binding),
        "memory_gib": memory_gib(config, binding),
        "prices_as_of": config.get("prices_as_of") or PRICES_AS_OF,
    }


def rate_usd_per_s(config: dict, binding) -> Decimal:
    p = prices(config, binding)
    rate = (_dec(p["gpu_usd_per_s"]) + _dec(p["cpu"]) * _dec(p["cpu_usd_per_core_s"])
            + _dec(p["memory_gib"]) * _dec(p["mem_usd_per_gib_s"]))
    return rate.quantize(Decimal("0.0000000001"), rounding=ROUND_CEILING)


def hold_usd(config: dict, binding, media_seconds: Optional[float], stats=None) -> Decimal:
    """
    The reservation of one attempt (spec 0003, 4.6.6).

    Worst case, while the key (engine, feature, gpu, E) has fewer than 50 settled
    successful job rows - every item assumed cold, at the slow end of the speed:

        (D / s_p20 + 15 + cold_s_p80) x rate x (1 + margin)

    with s_p20 / cold_s_p80 from the key's ledger rows, else its latest benchmark,
    else default_speed / E and the configured cold start. From 50 rows on, the
    learned cost, which already includes cold starts and sharing:

        D x q95(actual_usd / D) x (1 + margin)

    `stats` is a speed.SpeedStats (or None: the defaults).
    """
    if media_seconds is None:
        raise ValueError("A remote reservation needs the media duration")
    margin = _dec(config.get("margin", DEFAULT_MARGIN))
    if stats is not None and getattr(stats, "learned", False):
        return round_up(_dec(float(media_seconds)) * _dec(stats.usd_per_s_q95) * (1 + margin))
    speed, cold = worst_case_speed(config, binding, stats)
    seconds = _dec(float(media_seconds) / speed + FIXED_OVERHEAD_SECONDS + cold)
    return round_up(seconds * rate_usd_per_s(config, binding) * (1 + margin))


def worst_case_speed(config: dict, binding, stats=None):
    """(speed x real time per item, cold start seconds) the worst case uses"""
    speed = getattr(stats, "s_p20", None) if stats is not None else None
    if not speed or speed <= 0:
        speed = float(config.get("default_speed") or DEFAULT_SPEED) / binding.executions_per_worker
    cold = getattr(stats, "cold_s_p80", None) if stats is not None else None
    if cold is None:
        cold = float(config.get("cold_start_seconds") or DEFAULT_COLD_START_SECONDS)
    return float(speed), float(cold)


def deadline_seconds(reserved_usd: Decimal, rate: Decimal) -> float:
    """With E = 1 the reservation is the attempt's ceiling: it may run reserved / rate seconds"""
    if rate <= 0:
        raise ValueError("A remote attempt needs a positive rate")
    return float(_dec(reserved_usd) / _dec(rate))


def settle_usd(reported_seconds: Optional[float], measured_seconds: float, rate: Decimal) -> Decimal:
    """actual = max(reported, measured) x rate: the container cannot make itself cheaper (S7)"""
    seconds = max(float(reported_seconds or 0), float(measured_seconds or 0))
    return round_up(_dec(seconds) * _dec(rate))
