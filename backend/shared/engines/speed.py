"""
Learned speed and cost per key (engine, feature, gpu, executions_per_worker)
(spec 0003, 4.6.6 and Appendix D).

    s_p20          x real time per item, 20th percentile (the slow end) of the key's
                   last 200 settled successful job rows
    cold_s_p80     seconds of cold start, 80th percentile of the rows that had one
    usd_per_s_q95  US$ per media second, 95th percentile - only once the key has 50
                   successful job rows; until then a reservation is the worst case

A key without enough ledger rows (fewer than MIN_SPEED_SAMPLES) takes the latest
benchmark of that key, else the engine's default_speed / E. The ledger is the
source; Redis only caches (engine:{id}:{feature}:{gpu}:{E}:speed, 1 h), written
by worker-dispatch's beat and on a miss. Losing Redis only means recomputing.
"""

import logging
import math
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from shared.models import EngineUsage, JobDispatch

logger = logging.getLogger(__name__)

KEY = "engine:{engine_id}:{feature}:{gpu}:{e}:speed"
CACHE_TTL_SECONDS = 3600
WINDOW_ROWS = 200
Q95_AFTER_ROWS = 50  # successful kind=job rows before the learned q95 replaces the worst case
MIN_SPEED_SAMPLES = 5  # below this, a benchmark of the key (or the default) gives the speed


@dataclass
class SpeedStats:
    engine_id: str
    feature: str
    gpu: str
    executions_per_worker: int
    rows: int = 0  # successful settled job rows in the window
    s_p20: Optional[float] = None
    cold_s_p80: Optional[float] = None
    usd_per_s_q95: Optional[Decimal] = None
    source: str = "default"  # ledger | benchmark | default
    benchmark_usage_id: Optional[int] = None

    @property
    def learned(self) -> bool:
        """The q95 replaces the worst case (spec 0003, 4.6.6)"""
        return self.rows >= Q95_AFTER_ROWS and self.usd_per_s_q95 is not None

    def as_cache(self) -> Dict[str, str]:
        return {k: "" if v is None else str(v) for k, v in asdict(self).items()}

    @classmethod
    def from_cache(cls, raw: Dict) -> "SpeedStats":
        def text(name):
            value = raw.get(name)
            value = value.decode() if isinstance(value, bytes) else value
            return value if value not in (None, "") else None

        def num(name, kind=float):
            value = text(name)
            return kind(value) if value is not None else None

        return cls(engine_id=text("engine_id"), feature=text("feature"), gpu=text("gpu"),
                   executions_per_worker=int(text("executions_per_worker") or 1), rows=int(text("rows") or 0),
                   s_p20=num("s_p20"), cold_s_p80=num("cold_s_p80"),
                   usd_per_s_q95=num("usd_per_s_q95", Decimal), source=text("source") or "default",
                   benchmark_usage_id=num("benchmark_usage_id", int))

    def view(self) -> Dict[str, object]:
        return {"gpu": self.gpu, "executions_per_worker": self.executions_per_worker, "rows": self.rows,
                "s_p20": self.s_p20, "cold_s_p80": self.cold_s_p80,
                "usd_per_media_s_q95": str(self.usd_per_s_q95) if self.usd_per_s_q95 is not None else None,
                "usd_per_audio_hour_q95": (str((self.usd_per_s_q95 * 3600).quantize(Decimal("0.0001")))
                                           if self.usd_per_s_q95 is not None else None),
                "source": self.source, "learned": self.learned, "needs_rows": max(Q95_AFTER_ROWS - self.rows, 0)}


def cache_key(engine_id: str, feature: str, gpu: Optional[str], e: int) -> str:
    return KEY.format(engine_id=engine_id, feature=feature, gpu=gpu or "cpu", e=int(e or 1))


def quantile(values: List[float], q: float) -> Optional[float]:
    """Linear-interpolated quantile; None for no values"""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _media_seconds(row: EngineUsage, by_subject: Dict[tuple, float]) -> Optional[float]:
    units = row.units or {}
    value = units.get("media_seconds")
    if value is None:
        value = by_subject.get((row.subject_type, row.subject_id))
    try:
        value = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return value if value and value > 0 else None


def _exec_seconds(row: EngineUsage) -> Optional[float]:
    if row.exec_started_at and row.exec_ended_at:
        seconds = (row.exec_ended_at - row.exec_started_at).total_seconds()
    elif row.measured_seconds is not None:
        seconds = float(row.measured_seconds) - float(row.cold_start_seconds or 0)
    else:
        return None
    return seconds if seconds > 0 else None


def latest_benchmark(db: Session, engine_id: str, feature: str, gpu: Optional[str], e: int) -> Optional[EngineUsage]:
    return (db.query(EngineUsage)
            .filter(EngineUsage.engine_id == engine_id, EngineUsage.feature == feature,
                    EngineUsage.kind == "benchmark", EngineUsage.status == "settled",
                    EngineUsage.gpu_type == gpu, EngineUsage.executions_per_worker == e)
            .order_by(EngineUsage.finished_at.desc(), EngineUsage.id.desc()).first())


def compute(db: Session, engine_id: str, feature: str, gpu: Optional[str], e: int) -> SpeedStats:
    """The key's quantiles straight from the ledger"""
    e = int(e or 1)
    stats = SpeedStats(engine_id=engine_id, feature=feature, gpu=gpu or "cpu", executions_per_worker=e)
    rows = (db.query(EngineUsage)
            .filter(EngineUsage.engine_id == engine_id, EngineUsage.feature == feature, EngineUsage.kind == "job",
                    EngineUsage.status == "settled", EngineUsage.outcome == "succeeded",
                    EngineUsage.gpu_type == gpu, EngineUsage.executions_per_worker == e)
            .order_by(EngineUsage.finished_at.desc(), EngineUsage.id.desc()).limit(WINDOW_ROWS).all())
    stats.rows = len(rows)
    missing = [(r.subject_type, r.subject_id) for r in rows if (r.units or {}).get("media_seconds") is None
               and r.subject_id]
    by_subject: Dict[tuple, float] = {}
    if missing:
        ids = [s for _, s in missing]
        for subject_type, subject_id, media in db.query(JobDispatch.subject_type, JobDispatch.subject_id,
                                                        JobDispatch.media_seconds).filter(
                JobDispatch.subject_id.in_(ids)):
            if media is not None:
                by_subject[(subject_type, subject_id)] = float(media)

    speeds, colds, costs = [], [], []
    for row in rows:
        media = _media_seconds(row, by_subject)
        exec_s = _exec_seconds(row)
        if media and exec_s:
            speeds.append(media / exec_s)
        if row.cold_start_seconds is not None and float(row.cold_start_seconds) > 0:
            colds.append(float(row.cold_start_seconds))
        if media and row.actual_usd is not None:
            costs.append(Decimal(str(row.actual_usd)) / Decimal(str(media)))

    if len(speeds) >= MIN_SPEED_SAMPLES:
        stats.s_p20 = round(quantile(speeds, 0.2), 4)
        stats.cold_s_p80 = round(quantile(colds, 0.8), 3) if colds else None
        stats.source = "ledger"
    else:
        bench = latest_benchmark(db, engine_id, feature, gpu, e)
        result = ((bench.units or {}).get("result") or {}) if bench is not None else {}
        if result.get("speed_per_item_p20") or result.get("speed_per_item"):
            stats.s_p20 = float(result.get("speed_per_item_p20") or result["speed_per_item"])
            cold = result.get("cold_start_seconds")
            stats.cold_s_p80 = float(cold) if cold else None
            stats.source = "benchmark"
            stats.benchmark_usage_id = bench.id
    if stats.rows >= Q95_AFTER_ROWS and costs:
        q95 = quantile([float(c) for c in costs], 0.95)
        stats.usd_per_s_q95 = Decimal(str(q95)).quantize(Decimal("0.0000000001"))
    return stats


def _redis(redis_client=None):
    if redis_client is not None:  # a raw redis client, or the app's RedisClient wrapper (.client)
        return redis_client if hasattr(redis_client, "pipeline") else redis_client.client
    try:
        from shared.redis_client import get_redis_client
        return get_redis_client().client
    except Exception:
        return None


def write_cache(stats: SpeedStats, redis_client=None) -> None:
    client = _redis(redis_client)
    if client is None:
        return
    key = cache_key(stats.engine_id, stats.feature, stats.gpu, stats.executions_per_worker)
    try:
        pipe = client.pipeline()
        pipe.delete(key)
        pipe.hset(key, mapping=stats.as_cache())
        pipe.expire(key, CACHE_TTL_SECONDS)
        pipe.execute()
    except Exception as e:
        logger.debug(f"[ENGINES] Could not cache speed {key}: {type(e).__name__}")


def forget(engine_id: str, feature: str, gpu: Optional[str], e: int, redis_client=None) -> None:
    client = _redis(redis_client)
    if client is None:
        return
    try:
        client.delete(cache_key(engine_id, feature, gpu, e))
    except Exception:
        pass


def get_stats(db: Session, engine_id: str, feature: str, gpu: Optional[str], e: int,
              redis_client=None) -> SpeedStats:
    """The key's stats: from the 1 h cache, else from the ledger (and cached)"""
    client = _redis(redis_client)
    if client is not None:
        try:
            raw = client.hgetall(cache_key(engine_id, feature, gpu, e))
            if raw:
                return SpeedStats.from_cache(raw)
        except Exception:
            pass
    stats = compute(db, engine_id, feature, gpu, e)
    write_cache(stats, client)
    return stats


def refresh_all(db: Session, redis_client=None) -> List[SpeedStats]:
    """Recompute and cache every key an engine has a binding for (worker-dispatch's beat)"""
    from shared.engines.capacity import bindings
    from shared.models import Engine

    out = []
    for engine in db.query(Engine).all():
        try:
            by_feature = bindings(engine.config or {})
        except Exception:
            continue
        for feature, binding in by_feature.items():
            stats = compute(db, engine.id, feature, binding.gpu_type or binding.gpu_ref,
                            binding.executions_per_worker)
            write_cache(stats, redis_client)
            out.append(stats)
    return out
