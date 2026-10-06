"""
The benchmark command (spec 0003, 4.6.6 and Appendix H): speed, US$ per hour of
audio and VRAM per (gpu, E), and a recommendation.

    python scripts/engines.py benchmark --engine modal_1 --feature transcription \\
        --sample /tmp/ingestify/bench/a.mp3:240 --gpus T4,L4,A10G --concurrency 1 \\
        [--max-usd 1.00] [--yes] [--apply] [--experimental]

REMOTE (costs money; run in worker-remote, the only holder of the private keys):

    plan      per combination the pessimistic estimate
                  (cold_p80 + scaledown + sum(samples) x E / default_speed) x rate
              printed term by term with the total; refused above --max-usd (default
              1.00), with E > max_E without --experimental, or when the account's
              production workers + 1 exceed account_max_gpus
    confirm   interactive, or --yes
    reserve   --max-usd split over the combinations in proportion to their estimates,
              one `kind=benchmark` row each (placed_by=cli), under the engine's lock and
              the same budget formula as any reservation - so a benchmark stays inside
              the account's limit. Benchmark rows count as money, never as slots.
    run       each combination is an EPHEMERAL app (`modal run`, never the production
              app, never a deploy) built for that decorator, in a subprocess whose
              environment is built from scratch (token as variables, HOME a temp dir);
              its deadline is its share / rate, counted from the moment the app is up -
              then it is interrupted. Before each one: spent so far + its estimate
              > --max-usd => stop and report what was measured.
    settle    actual = seconds the app was up x rate (whole subprocess when it was cut)

LOCAL (free, but shares the card): never inside a live worker - a one-off
container (`docker compose run --rm --no-deps worker-audio python -m
workers.engines.benchmark ... --here`), which first passes the VRAM guard against
what is resident: used now (nvidia-smi) + E x footprint + reserve <= VRAM, else
refused with the arithmetic. --pause-local pauses the local engine and waits for
its in-flight work; without it results are marked `contended`.

OUTPUT: a gpu x E table (speed per item, aggregate speed, US$/h of audio, peak VRAM,
cold start, cost), the fit base_gb + E x per_exec_gb per GPU (local), and the
recommendation: lowest US$/h whose VRAM fits and whose per-item speed >= min_speed
(local: all free, so the fastest aggregate). --apply writes it: remote, the binding
(gpu_type, E) - which then needs a redeploy; local, the replicas and the measured
per-process footprint (x 1.1) as vram_override_gb. Results stay in the benchmark
rows' `units` and feed the key's speed quantiles (shared/engines/speed.py).
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import update

from shared.engines import budget, ledger, pricing, speed
from shared.engines.capacity import MODAL_MAX_E, Binding, CapacityError, bindings, footprint_gb, LocalGpu
from shared.engines.gpus import DEFAULT_ACCOUNT_MAX_GPUS, DEFAULT_VRAM_RESERVE_GB, MODAL_GPUS
from shared.models import Engine, EngineUsage

logger = logging.getLogger(__name__)

DEFAULT_MAX_USD = Decimal("1.00")
HEARTBEAT_SECONDS = 15
STARTUP_TIMEOUT_SECONDS = 900  # image build and app start, before any GPU container exists
INTERRUPT_GRACE_SECONDS = 20
LOCAL_TIMEOUT_SECONDS = 2 * 3600
VRAM_FIT_MARGIN = 1.1
BENCH_MODULE = "workers.engines.modal_apps.bench_entry"


class BenchmarkError(Exception):
    """A benchmark that must not run (or stop); the message says why"""

    def __init__(self, message: str, lines: Optional[List[str]] = None):
        super().__init__(message)
        self.lines = lines or []


def qualification_options(settings, manifest=None):
    """Measure the complete WhisperX pipeline, including diarization/alignment.

    A remote canary takes model identities from its own deployment manifest;
    local runs use the same durable configuration as admitted jobs.
    """
    from shared.transcription import normalize_options, make_profile, options_from_profile
    if manifest is not None:
        from workers.engines.modal_apps.protocol import MODEL_NAME
        settings = settings.model_copy(update={
            'audio_transcriber_provider': 'whisperx',
            'whisper_model': manifest['asr'].get('model', MODEL_NAME),
            'whisperx_asr_revision': manifest['asr']['revision'],
            'whisperx_vad_revision': manifest['vad']['revision'],
            'whisperx_diarization_model': manifest['diarizer'].get('model', settings.whisperx_diarization_model),
            'whisperx_diarization_revision': manifest['diarizer']['revision'],
            'whisperx_aligner_manifest': json.dumps(manifest['aligners'], sort_keys=True),
        })
    full_pipeline = settings.audio_transcriber_provider == 'whisperx'
    options = normalize_options(settings, {'diarize': full_pipeline,
                                          'include_word_timestamps': full_pipeline})
    return options_from_profile(make_profile(settings, options), options)


@dataclass
class Sample:
    path: str
    seconds: float


@dataclass
class Combination:
    gpu: str
    e: int
    rate: Decimal = Decimal("0")
    estimate_usd: Decimal = Decimal("0")
    terms: Dict[str, float] = field(default_factory=dict)
    share_usd: Decimal = Decimal("0")
    deadline_seconds: Optional[float] = None
    usage_id: Optional[int] = None


@dataclass
class ItemTiming:
    media_seconds: float
    exec_seconds: float
    cold_start_seconds: float = 0.0
    wall_seconds: float = 0.0


@dataclass
class RunResult:
    completed: bool
    billed_seconds: float  # seconds the GPU could have been billed (remote) / the run lasted (local)
    window_seconds: float  # first item start -> last item end
    items: List[ItemTiming] = field(default_factory=list)
    vram_baseline_gb: Optional[float] = None
    vram_peak_gb: Optional[float] = None
    error: Optional[str] = None


@dataclass
class Plan:
    engine_id: str
    slug: str
    adapter_type: str
    feature: str
    samples: List[Sample]
    combinations: List[Combination]
    max_usd: Decimal
    total_usd: Decimal = Decimal("0")
    contended: bool = False

    @property
    def remote(self) -> bool:
        return self.adapter_type != "local"


# --- planning ---------------------------------------------------------------------------------


def parse_samples(specs: List[str], measure: Optional[Callable[[str], Optional[float]]] = None) -> List[Sample]:
    """`path` or `path:seconds`; without seconds the duration is probed (needs PyAV: worker images)"""
    samples = []
    for spec in specs:
        path, _, seconds = spec.rpartition(":") if spec.rsplit(":", 1)[-1].replace(".", "", 1).isdigit() \
            else (spec, "", "")
        if not Path(path).is_file():
            raise BenchmarkError(f"Sample {path} is not a file (inside the container that runs the benchmark)")
        if seconds:
            value = float(seconds)
        else:
            if measure is None:
                from shared.engines.media import probe_duration
                measure = lambda p: probe_duration(p, 64 * 1024 * 1024)  # noqa: E731
            try:
                value = measure(path)
            except Exception:
                value = None
            if not value:
                raise BenchmarkError(f"Could not read the duration of {path}: pass it as {path}:<seconds>")
        if value <= 0:
            raise BenchmarkError(f"Sample {path} has no duration")
        samples.append(Sample(path, float(value)))
    if not samples:
        raise BenchmarkError("At least one --sample is needed")
    return samples


def _production_workers(engine: Engine) -> int:
    return sum(b.workers for b in bindings(engine.config or {}).values())


def plan_remote(db, engine: Engine, feature: str, samples: List[Sample], gpus: List[str], concurrency: List[int],
                max_usd: Decimal = DEFAULT_MAX_USD, experimental: bool = False) -> Plan:
    """The pessimistic estimate of every (gpu, E); raises BenchmarkError when it must not run"""
    config = engine.config or {}
    max_gpus = int(config.get("account_max_gpus") or DEFAULT_ACCOUNT_MAX_GPUS)
    if _production_workers(engine) + 1 > max_gpus:
        raise BenchmarkError(f"{engine.slug}: production workers ({_production_workers(engine)}) + 1 benchmark "
                             f"container exceed account_max_gpus={max_gpus}")
    media = sum(s.seconds for s in samples)
    default_speed = float(config.get("default_speed") or pricing.DEFAULT_SPEED)
    scaledown = float(config.get("scaledown_window") or pricing.DEFAULT_SCALEDOWN_WINDOW)
    combos = []
    for gpu in gpus:
        if gpu not in MODAL_GPUS:
            raise BenchmarkError(f"Unknown GPU {gpu!r}; one of {', '.join(MODAL_GPUS)}")
        for e in concurrency:
            if e < 1:
                raise BenchmarkError("--concurrency values are >= 1")
            if e > MODAL_MAX_E and not experimental:
                raise BenchmarkError(f"E={e} needs --experimental until gates T4/T8 pass with max_inputs >= 2 "
                                     f"(the measurement is what gate T8 needs)")
            binding = Binding(gpu_type=gpu, workers=1, executions_per_worker=e)
            stats = speed.get_stats(db, engine.id, feature, gpu, e)
            cold = stats.cold_s_p80 if stats.cold_s_p80 is not None else \
                float(config.get("cold_start_seconds") or pricing.DEFAULT_COLD_START_SECONDS)
            rate = pricing.rate_usd_per_s(config, binding)
            seconds = cold + scaledown + media * e / default_speed
            combos.append(Combination(gpu=gpu, e=e, rate=rate,
                                      estimate_usd=pricing.round_up(Decimal(str(seconds)) * rate),
                                      terms={"cold_p80_s": round(cold, 1), "scaledown_s": scaledown,
                                             "media_s": round(media * e, 1), "default_speed": default_speed,
                                             "seconds": round(seconds, 1)}))
    plan = Plan(engine.id, engine.slug, engine.adapter_type, feature, samples, combos, Decimal(str(max_usd)))
    plan.total_usd = sum((c.estimate_usd for c in combos), Decimal("0"))
    if plan.total_usd > plan.max_usd:
        raise BenchmarkError(f"The pessimistic estimate US$ {plan.total_usd} is above --max-usd {plan.max_usd}: "
                             f"fewer GPUs, shorter samples or a higher --max-usd", describe(plan))
    for c in combos:  # each combination may spend its share of --max-usd, and is cut there
        c.share_usd = pricing.round_up(plan.max_usd * c.estimate_usd / plan.total_usd) if plan.total_usd else \
            plan.max_usd
        c.deadline_seconds = pricing.deadline_seconds(c.share_usd, c.rate)
    return plan


def plan_local(engine: Engine, feature: str, samples: List[Sample], gpus: List[str], concurrency: List[int],
               pause_local: bool = False) -> Plan:
    declared = {g["ref"]: g for g in (engine.config or {}).get("gpus") or []}
    if not gpus:
        gpus = list(declared)
    for ref in gpus:
        if ref not in declared:
            raise BenchmarkError(f"GPU {ref!r} is not declared on the local engine (engines.py set-gpus)")
    combos = [Combination(gpu=ref, e=e) for ref in gpus for e in concurrency]
    return Plan(engine.id, engine.slug, "local", feature, samples, combos, Decimal("0"), contended=not pause_local)


def describe(plan: Plan) -> List[str]:
    lines = [f"Benchmark of {plan.slug} ({plan.feature}): {len(plan.samples)} sample(s), "
             f"{sum(s.seconds for s in plan.samples):.0f} s of media"]
    for c in plan.combinations:
        if plan.remote:
            t = c.terms
            lines.append(f"  {c.gpu:<10} E={c.e}: ({t['cold_p80_s']} cold + {t['scaledown_s']:.0f} scaledown + "
                         f"{t['media_s']} s x E / {t['default_speed']:g}x) = {t['seconds']} s x US$ {c.rate}/s "
                         f"= US$ {c.estimate_usd}" + (f"; cut at US$ {c.share_usd} ({c.deadline_seconds:.0f} s)"
                                                      if c.deadline_seconds else ""))
        else:
            lines.append(f"  {c.gpu:<10} E={c.e}: local, free")
    if plan.remote:
        lines.append(f"  total (pessimistic) US$ {plan.total_usd}; hard cap --max-usd US$ {plan.max_usd}")
    return lines


# --- the ledger -------------------------------------------------------------------------------


def reserve(plan: Plan, holder: str, *, session_factory=None, now: Optional[datetime] = None) -> List[int]:
    """One reserved benchmark row per combination, all or none, under the engine's lock and budget"""
    now = now or datetime.utcnow()
    total = sum((c.share_usd for c in plan.combinations), Decimal("0"))

    def work(db):
        engine = db.query(Engine).filter(Engine.id == plan.engine_id).with_for_update().one()
        if engine.limit_usd is None:
            raise BenchmarkError(f"{engine.slug} has no budget (engines.py budget {engine.slug} --limit-usd ...)")
        period = budget.period_start(engine, now)
        if not budget.admits(db, engine, total, period):
            room = budget.headroom(db, engine, period)
            raise BenchmarkError(f"{engine.slug} cannot reserve US$ {total}: US$ {room} left in this period "
                                 f"(limit - min_remaining - spent - reserved); lower --max-usd")
        ids = []
        for c in plan.combinations:
            binding = Binding(gpu_type=c.gpu, workers=1, executions_per_worker=c.e)
            row = EngineUsage(kind="benchmark", engine_id=engine.id, feature=plan.feature, period_start=period,
                              status="reserved", placed_by="cli", gpu_type=c.gpu, executions_per_worker=c.e,
                              estimated_usd=c.estimate_usd, reserved_usd=c.share_usd, rate_usd_per_s=c.rate,
                              price_snapshot=pricing.prices(engine.config or {}, binding), holder=holder,
                              heartbeat_at=now, created_at=now, counts_toward_attempts=False,
                              units={"plan": c.terms, "samples": len(plan.samples)})
            db.add(row)
            db.flush()
            ids.append(row.id)
        return ids

    ids = ledger.run_txn(session_factory, work)
    for c, usage_id in zip(plan.combinations, ids):
        c.usage_id = usage_id
    return ids


def _set_running(usage_id: int, holder: str, session_factory, now: datetime) -> bool:
    def work(db):
        return db.execute(update(EngineUsage).where(EngineUsage.id == usage_id, EngineUsage.status == "reserved")
                          .values(status="running", holder=holder, heartbeat_at=now, spawned_at=now)
                          .execution_options(synchronize_session=False)).rowcount == 1
    return ledger.run_txn(session_factory, work)


def _heartbeat(usage_id: int, holder: str, session_factory) -> None:
    try:
        ledger.heartbeat(usage_id, holder, session_factory=session_factory)
    except Exception as e:
        logger.warning(f"[ENGINES] Benchmark heartbeat of usage {usage_id} failed: {type(e).__name__}")


def release_rows(usage_ids: List[int], session_factory, now: datetime, reason: str = "BENCHMARK_STOPPED") -> None:
    def work(db):
        db.execute(update(EngineUsage).where(EngineUsage.id.in_(usage_ids), EngineUsage.status == "reserved")
                   .values(status="released", finished_at=now, actual_usd=0, error_code=reason)
                   .execution_options(synchronize_session=False))
    if usage_ids:
        ledger.run_txn(session_factory, work)


def metrics(combo: Combination, result: RunResult) -> Dict[str, Any]:
    """What a combination measured; also what its ledger row keeps in units.result"""
    items = [i for i in result.items if i.exec_seconds > 0 and i.media_seconds > 0]
    per_item = [i.media_seconds / i.exec_seconds for i in items]
    media = sum(i.media_seconds for i in items)
    aggregate = media / result.window_seconds if result.window_seconds > 0 and media else None
    usd_h = (combo.rate * 3600 / Decimal(str(aggregate))).quantize(Decimal("0.0001")) \
        if aggregate and combo.rate > 0 else (Decimal("0") if aggregate else None)
    cost = pricing.round_up(Decimal(str(result.billed_seconds)) * combo.rate) if combo.rate > 0 else Decimal("0")
    colds = [i.cold_start_seconds for i in items if i.cold_start_seconds]
    return {
        "gpu": combo.gpu, "executions_per_worker": combo.e, "completed": result.completed, "items": len(items),
        "media_seconds": round(media, 1),
        "speed_per_item": round(speed.quantile(per_item, 0.5), 3) if per_item else None,
        "speed_per_item_p20": round(speed.quantile(per_item, 0.2), 3) if per_item else None,
        "speed_aggregate": round(aggregate, 3) if aggregate else None,
        "usd_per_audio_hour": str(usd_h) if usd_h is not None else None,
        "cold_start_seconds": round(max(colds), 2) if colds else None,
        "vram_baseline_gb": result.vram_baseline_gb, "vram_peak_gb": result.vram_peak_gb,
        "vram_used_gb": (round(result.vram_peak_gb - (result.vram_baseline_gb or 0), 2)
                         if result.vram_peak_gb is not None else None),
        "cost_usd": str(cost), "billed_seconds": round(result.billed_seconds, 1), "error": result.error,
    }


def settle(combo: Combination, result: RunResult, plan: Plan, holder: str, *, session_factory=None,
           now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.utcnow()
    m = metrics(combo, result)
    outcome = "succeeded" if result.completed else ("failed" if result.error else "cancelled")

    def work(db):
        values = dict(status="settled", outcome=outcome, actual_usd=Decimal(m["cost_usd"]), finished_at=now,
                      cost_basis="measured", measured_seconds=round(result.billed_seconds, 3),
                      cold_start_seconds=m["cold_start_seconds"], counts_toward_attempts=False,
                      units={"plan": combo.terms, "samples": len(plan.samples), "contended": plan.contended,
                             "result": m},
                      error_code=None if result.completed else ("BENCHMARK_ERROR" if result.error else "DEADLINE"),
                      error_detail=(result.error or "")[:2000] or None)
        return db.execute(update(EngineUsage).where(EngineUsage.id == combo.usage_id,
                                                    EngineUsage.status.in_(ledger.IN_FLIGHT))
                          .values(**values).execution_options(synchronize_session=False)).rowcount == 1

    ledger.run_txn(session_factory, work)
    speed.forget(plan.engine_id, plan.feature, combo.gpu, combo.e)
    return m


def record_local(combo: Combination, result: RunResult, plan: Plan, *, session_factory=None,
                 now: Optional[datetime] = None) -> Dict[str, Any]:
    """A local combination: a settled, free benchmark row"""
    now = now or datetime.utcnow()

    def work(db):
        engine = db.get(Engine, plan.engine_id)
        row = EngineUsage(kind="benchmark", engine_id=plan.engine_id, feature=plan.feature,
                          period_start=budget.period_start(engine, now), status="reserved", placed_by="cli",
                          gpu_type=combo.gpu, executions_per_worker=combo.e, estimated_usd=0, reserved_usd=0,
                          rate_usd_per_s=0, heartbeat_at=now, created_at=now, counts_toward_attempts=False)
        db.add(row)
        db.flush()
        return row.id

    combo.usage_id = ledger.run_txn(session_factory, work)
    return settle(combo, result, plan, "cli", session_factory=session_factory, now=now)


# --- recommendation, VRAM fit, apply ----------------------------------------------------------


def fit_vram(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Per GPU, least squares of measured VRAM = base_gb + E x per_exec_gb over the E grid (R18)"""
    out = {}
    by_gpu: Dict[str, List[Tuple[int, float]]] = {}
    for r in results:
        if r.get("vram_used_gb") is not None:
            by_gpu.setdefault(r["gpu"], []).append((r["executions_per_worker"], float(r["vram_used_gb"])))
    for gpu, points in by_gpu.items():
        if len({e for e, _ in points}) >= 2:
            n = len(points)
            mean_e = sum(e for e, _ in points) / n
            mean_v = sum(v for _, v in points) / n
            per = sum((e - mean_e) * (v - mean_v) for e, v in points) / sum((e - mean_e) ** 2 for e, _ in points)
            base = mean_v - per * mean_e
        else:
            e, v = points[0]
            base, per = 0.0, v / e
        per = max(per, 0.0)
        base = max(base, 0.0)
        out[gpu] = {"base_gb": round(base, 3), "per_exec_gb": round(per, 3),
                    "footprint_e1_gb": round((base + per) * VRAM_FIT_MARGIN, 2)}
    return out


def _vram_of(plan: Plan, engine: Engine, gpu: str) -> Tuple[float, float]:
    if plan.remote:
        return float(MODAL_GPUS[gpu].vram_gb), DEFAULT_VRAM_RESERVE_GB
    for raw in (engine.config or {}).get("gpus") or []:
        g = LocalGpu(**raw)
        if g.ref == gpu:
            return g.vram_gb, g.vram_reserve_gb
    return 0.0, DEFAULT_VRAM_RESERVE_GB


def recommend(plan: Plan, engine: Engine, results: List[Dict[str, Any]], fit: Dict[str, Dict[str, float]],
              vision_model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Lowest US$/h of audio that fits in VRAM and keeps each item at >= min_speed (free: fastest aggregate)"""
    min_speed = float((engine.config or {}).get("min_speed") or pricing.DEFAULT_MIN_SPEED)
    default_each = footprint_gb(plan.feature, Binding(workers=1), vision_model_id)
    candidates = []
    for r in results:
        if not r["completed"] or r["speed_aggregate"] is None or (r["speed_per_item"] or 0) < min_speed:
            continue
        vram, reserve_gb = _vram_of(plan, engine, r["gpu"])
        if r.get("vram_peak_gb") is not None:
            needed = float(r["vram_peak_gb"]) + reserve_gb
        elif r["gpu"] in fit:
            f = fit[r["gpu"]]
            needed = (f["base_gb"] + r["executions_per_worker"] * f["per_exec_gb"]) * VRAM_FIT_MARGIN + reserve_gb
        else:
            needed = r["executions_per_worker"] * default_each + reserve_gb
        if needed > vram:
            continue
        cost = Decimal(r["usd_per_audio_hour"] or "0")
        candidates.append((cost, -float(r["speed_aggregate"]), r))
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c[0], c[1]))[2]


def apply(plan: Plan, best: Dict[str, Any], fit: Dict[str, Dict[str, float]], *, session_factory=None,
          vision_model_id: Optional[str] = None) -> str:
    """Write the recommendation: remote binding (needs a redeploy), or local replicas + measured footprint"""
    from shared.engines import store

    db = ledger._session(session_factory)
    try:
        engine = db.get(Engine, plan.engine_id)
        current = bindings(engine.config or {}).get(plan.feature)
        if plan.remote:
            binding = Binding(gpu_type=best["gpu"], workers=current.workers if current else 1,
                              executions_per_worker=best["executions_per_worker"],
                              cpu=current.cpu if current else None,
                              vram_override_gb=current.vram_override_gb if current else None)
            what = (f"{engine.slug} {plan.feature}: gpu_type={binding.gpu_type}, E={binding.executions_per_worker} "
                    f"- needs `engines.py modal-deploy --engine {engine.slug}` before it takes items")
        else:
            footprint = fit.get(best["gpu"], {}).get("footprint_e1_gb")
            binding = Binding(gpu_ref=best["gpu"], workers=best["executions_per_worker"], executions_per_worker=1,
                              vram_override_gb=footprint or (current.vram_override_gb if current else None))
            from shared.engines.features import get_feature
            what = (f"local {plan.feature}: {binding.workers} replica(s) on {binding.gpu_ref}, "
                    f"{binding.vram_override_gb or 'default'} GB each - then "
                    + get_feature(plan.feature).scale_hint.format(workers=binding.workers))
        store.set_binding(db, engine, plan.feature, binding, version=None, actor_user_id=None, auth_method="cli",
                          vision_model_id=vision_model_id)
        return what
    except CapacityError as e:
        db.rollback()
        raise BenchmarkError(f"--apply refused: {e}", e.lines) from None
    finally:
        db.close()


# --- remote runner: one ephemeral Modal app per combination ------------------------------------


class ModalBenchRunner:
    """
    Runs `python -m modal run -m workers.engines.modal_apps.bench_entry::bench` with
    the combination's deploy spec, so Modal builds an ephemeral app for exactly that
    decorator. The entrypoint prints a start marker once the app is up, then one
    line with every item's timings; the deadline counts from the start marker.
    """

    def __init__(self, engine: Engine, adapter, feature: str = "transcription", *, popen=subprocess.Popen,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 startup_timeout: float = STARTUP_TIMEOUT_SECONDS, allow_unhashed: bool = False):
        self.engine, self.adapter, self.feature = engine, adapter, feature
        self.popen, self.clock, self.sleep = popen, clock, sleep
        self.startup_timeout = startup_timeout
        self.allow_unhashed = allow_unhashed

    def command(self) -> List[str]:
        return [sys.executable, "-m", "modal", "run", "-m", f"{BENCH_MODULE}::bench"]

    def env(self, home: str, combo: Combination, samples: List[Sample]) -> Dict[str, str]:
        from workers.engines.modal_apps import bench_protocol
        from workers.engines.modal_apps.files import ALLOW_UNHASHED_ENV, BACKEND_DIR, DEPLOY_ENV
        from workers.engines.modal_apps.fingerprint import deploy_spec

        binding = Binding(gpu_type=combo.gpu, workers=1, executions_per_worker=combo.e)
        spec = deploy_spec(self.feature, self.engine.config or {}, binding)
        bench = {"samples": [s.path for s in samples], "executions": combo.e,
                 "deadline_seconds": combo.deadline_seconds}
        extra = {DEPLOY_ENV: json.dumps(spec, sort_keys=True), bench_protocol.BENCH_ENV: json.dumps(bench),
                 "PYTHONPATH": str(BACKEND_DIR)}
        if spec.get('whisperx_manifest'):
            from shared.config import get_settings
            settings = get_settings()
            bench['options'] = qualification_options(settings, spec['whisperx_manifest'])
            extra[bench_protocol.BENCH_ENV] = json.dumps(bench)
            extra['WHISPERX_MODEL_DIR'] = settings.whisperx_model_dir
        if self.allow_unhashed:
            extra[ALLOW_UNHASHED_ENV] = "1"
        return self.adapter.subprocess_env(home, extra)

    def __call__(self, combo: Combination, samples: List[Sample], heartbeat: Callable[[], None]) -> RunResult:
        from workers.engines.modal_apps import bench_protocol
        from workers.engines.modal_apps.files import BACKEND_DIR

        lines: List[str] = []

        def read(stream) -> None:
            for line in iter(stream.readline, ""):
                lines.append(line)

        with tempfile.TemporaryDirectory(prefix="modal-bench-home-") as home:
            process = self.popen(self.command(), env=self.env(home, combo, samples), cwd=str(BACKEND_DIR),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            reader = threading.Thread(target=read, args=(process.stdout,), daemon=True)
            reader.start()
            launched = self.clock()
            started_at = None
            last_beat = launched
            cut = None
            while process.poll() is None:
                now = self.clock()
                if started_at is None and any(bench_protocol.STARTED in line for line in list(lines)):
                    started_at = now
                if now - last_beat >= HEARTBEAT_SECONDS:
                    heartbeat()
                    last_beat = now
                if started_at is None and now - launched > self.startup_timeout:
                    cut = f"the app did not start within {self.startup_timeout:.0f} s"
                elif started_at is not None and combo.deadline_seconds and now - started_at > combo.deadline_seconds:
                    cut = f"deadline: {combo.deadline_seconds:.0f} s (its share of --max-usd) passed"
                if cut:
                    self._interrupt(process)
                    break
                self.sleep(1.0)
            ended = self.clock()
            reader.join(timeout=5)
        from shared.engines.redact import redact

        output = redact("".join(lines))
        done = bench_protocol.parse_output(output)
        if cut or done is None:
            # Cut, or no result: bill from the app's start (or launch) to the end, conservatively
            billed = ended - (started_at if started_at is not None else launched)
            items = [ItemTiming(**i) for i in (done or {}).get("items", [])]
            return RunResult(False, billed, 0.0, items, error=None if cut else (output[-1500:] or "no output"))
        items = [ItemTiming(**i) for i in done["items"]]
        return RunResult(True, max(done["ended"] - done["started"], 0.0), done.get("window_seconds") or 0.0, items)

    def _interrupt(self, process) -> None:
        import signal

        try:
            process.send_signal(signal.SIGINT)  # `modal run` stops the ephemeral app on Ctrl-C
            process.wait(timeout=INTERRUPT_GRACE_SECONDS)
        except Exception:
            process.kill()


# --- local runner: E processes on the card, in a one-off container -----------------------------


def gpu_memory() -> Optional[Dict[str, float]]:
    from workers.engines.heartbeat import detect_gpu

    gpu = detect_gpu()
    if not gpu:
        return None
    return {"total_gb": float(gpu["vram_total_gb"]), "used_gb": float(gpu["vram_used_gb"]), "uuid": gpu["gpu_uuid"]}


def local_vram_guard(engine: Engine, feature: str, gpu_ref: str, e: int, used_gb: float,
                     vision_model_id: Optional[str] = None) -> List[str]:
    """used now + E x footprint + reserve <= VRAM of the declared GPU; raises with the arithmetic"""
    vram, reserve_gb = None, DEFAULT_VRAM_RESERVE_GB
    for raw in (engine.config or {}).get("gpus") or []:
        g = LocalGpu(**raw)
        if g.ref == gpu_ref:
            vram, reserve_gb = g.vram_gb, g.vram_reserve_gb
    if vram is None:
        raise BenchmarkError(f"GPU {gpu_ref!r} is not declared on the local engine")
    current = bindings(engine.config or {}).get(feature)
    each = footprint_gb(feature, current or Binding(workers=1), vision_model_id)
    total = used_gb + e * each + reserve_gb
    line = (f"{gpu_ref}: used now {used_gb:.2f} + {e} x {each:g} ({feature}) + reserve {reserve_gb:g} "
            f"= {total:.2f} GB of {vram:g} GB")
    if total > vram + 1e-9:
        raise BenchmarkError(f"E={e} does not fit next to what is resident on {gpu_ref}", [line + " - does NOT fit"])
    return [line + " - fits"]


def _local_process(samples: List[Tuple[str, float]], model_name: str, compute_type: str, out) -> None:
    """One local execution: its own model and CUDA context, like one replica"""
    from shared.config import get_settings
    from workers.audio.factory import get_audio_transcriber
    settings = get_settings()
    started = time.time()
    transcriber = get_audio_transcriber()
    cold = time.time() - started
    options = qualification_options(settings)
    for path, seconds in samples:
        t0 = time.time()
        transcriber.transcribe(Path(path), options)
        t1 = time.time()
        out.put({"media_seconds": seconds, "exec_seconds": t1 - t0, "cold_start_seconds": cold,
                 "wall_seconds": t1 - t0, "start": t0, "end": t1})
        cold = 0.0


def run_local(combo: Combination, samples: List[Sample], heartbeat: Callable[[], None]) -> RunResult:
    import multiprocessing as mp

    from shared.config import get_settings

    settings = get_settings()
    compute = settings.whisper_compute_type if settings.whisper_compute_type not in ("", "auto") else "float16"
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    baseline = gpu_memory()
    peak = baseline["used_gb"] if baseline else None
    started = time.time()
    processes = [ctx.Process(target=_local_process,
                             args=([(s.path, s.seconds) for s in samples], settings.whisper_model, compute, queue))
                 for _ in range(combo.e)]
    for p in processes:
        p.start()
    while any(p.is_alive() for p in processes) and time.time() - started < LOCAL_TIMEOUT_SECONDS:
        now_mem = gpu_memory()
        if now_mem and (peak is None or now_mem["used_gb"] > peak):
            peak = now_mem["used_gb"]
        time.sleep(1.0)
    for p in processes:
        if p.is_alive():
            p.kill()
        p.join(timeout=10)
    raw = []
    while not queue.empty():
        raw.append(queue.get())
    completed = len(raw) == combo.e * len(samples) and all(p.exitcode == 0 for p in processes)
    window = (max(r["end"] for r in raw) - min(r["start"] for r in raw)) if raw else 0.0
    items = [ItemTiming(r["media_seconds"], r["exec_seconds"], r["cold_start_seconds"], r["wall_seconds"])
             for r in raw]
    return RunResult(completed, time.time() - started, window, items,
                     vram_baseline_gb=baseline["used_gb"] if baseline else None, vram_peak_gb=peak,
                     error=None if completed else "a local benchmark process failed or timed out")


# --- the whole command ------------------------------------------------------------------------


def run_plan(plan: Plan, runner: Callable[[Combination, List[Sample], Callable[[], None]], RunResult], *,
             session_factory=None, out: Callable[[str], None] = print, clock=datetime.utcnow,
             before_each: Optional[Callable[[Combination], None]] = None) -> List[Dict[str, Any]]:
    """Run the combinations in order under the hard cap; returns each one's metrics"""
    holder = f"benchmark:{ledger.holder_id()}"
    results = []
    if plan.remote:
        reserve(plan, holder, session_factory=session_factory, now=clock())
    spent = Decimal("0")
    try:
        for i, combo in enumerate(plan.combinations):
            if plan.remote and spent + combo.estimate_usd > plan.max_usd:
                out(f"Stopping: spent US$ {spent} + next estimate US$ {combo.estimate_usd} > --max-usd {plan.max_usd}")
                break
            if before_each is not None:
                before_each(combo)
            out(f"Running {combo.gpu} E={combo.e} ...")
            if plan.remote:
                if not _set_running(combo.usage_id, holder, session_factory, clock()):
                    out(f"Benchmark row {combo.usage_id} is no longer reserved: stopping")
                    break
                result = runner(combo, plan.samples, lambda c=combo: _heartbeat(c.usage_id, holder, session_factory))
                m = settle(combo, result, plan, holder, session_factory=session_factory, now=clock())
                spent += Decimal(m["cost_usd"])
            else:
                result = runner(combo, plan.samples, lambda: None)
                m = record_local(combo, result, plan, session_factory=session_factory, now=clock())
            results.append(m)
            out(f"  -> {'done' if m['completed'] else 'CUT/FAILED'}: per item {m['speed_per_item']}x, aggregate "
                f"{m['speed_aggregate']}x, US$/h of audio {m['usd_per_audio_hour']}, cost US$ {m['cost_usd']}")
    finally:
        if plan.remote:
            release_rows([c.usage_id for c in plan.combinations if c.usage_id], session_factory, clock())
            from shared.engines import budget_watch
            budget_watch.check(plan.engine_id, session_factory=session_factory, now=clock())
    return results


def table(results: List[Dict[str, Any]]) -> List[str]:
    lines = [f"{'gpu':<10} {'E':>2} {'per item':>9} {'aggregate':>9} {'US$/h aud':>10} {'VRAM GB':>8} "
             f"{'cold s':>7} {'cost US$':>9}"]
    for r in results:
        vram = r["vram_used_gb"] if r["vram_used_gb"] is not None else "-"
        lines.append(f"{r['gpu']:<10} {r['executions_per_worker']:>2} {str(r['speed_per_item']):>9} "
                     f"{str(r['speed_aggregate']):>9} {str(r['usd_per_audio_hour']):>10} {str(vram):>8} "
                     f"{str(r['cold_start_seconds']):>7} {r['cost_usd']:>9}" + ("" if r["completed"] else "  (cut)"))
    return lines


def local_container_command(args_line: str) -> str:
    return ("docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --no-deps "
            "-v \"$PWD/tmp/bench:/bench:ro\" worker-audio python -m workers.engines.benchmark " + args_line + " --here")


def main(argv=None, *, session_factory=None, out: Callable[[str], None] = print,
         confirm: Callable[[str], bool] = None, runner=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="benchmark", description="Benchmark an engine (spec 0003, Appendix H)")
    add_arguments(parser)
    args = parser.parse_args(argv)
    return run_command(args, session_factory=session_factory, out=out, confirm=confirm, runner=runner)


def add_arguments(parser) -> None:
    parser.add_argument("--engine", required=True, help="slug: local or modal_N")
    parser.add_argument("--feature", default="transcription")
    parser.add_argument("--sample", action="append", required=True,
                        help="media file, optionally path:seconds (repeatable); a few minutes each is plenty")
    parser.add_argument("--gpus", default="", help="remote: e.g. T4,L4,A10G; local: declared refs (default all)")
    parser.add_argument("--concurrency", default="1", help="E values, e.g. 1,2,4")
    parser.add_argument("--max-usd", type=Decimal, default=DEFAULT_MAX_USD, help="hard cap of the whole run")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--apply", action="store_true", help="write the recommended binding")
    parser.add_argument("--experimental", action="store_true", help="remote E > 1 before gates T4/T8")
    parser.add_argument("--plan", action="store_true", help="only print the plan and the estimate")
    parser.add_argument("--pause-local", action="store_true", help="local: pause the local engine while measuring")
    parser.add_argument("--here", action="store_true", help="local: run in this process (the one-off container)")
    parser.add_argument("--allow-unhashed", action="store_true", help="remote: like modal-deploy --allow-unhashed")


def run_command(args, *, session_factory=None, out: Callable[[str], None] = print, confirm=None, runner=None) -> int:
    from shared.config import get_settings

    vision_model_id = get_settings().vision_model_id
    confirm = confirm or (lambda question: input(question).strip().lower() in ("y", "yes", "s", "sim"))
    db = ledger._session(session_factory)
    try:
        engine = db.query(Engine).filter(Engine.slug == args.engine).first()
        if engine is None:
            out(f"❌ No engine {args.engine!r}")
            return 1
        db.expunge(engine)
        gpus = [g.strip() for g in args.gpus.split(",") if g.strip()]
        concurrency = [int(e) for e in str(args.concurrency).split(",") if e.strip()]
        samples = parse_samples(args.sample)
        if engine.adapter_type == "local":
            plan = plan_local(engine, args.feature, samples, gpus, concurrency, pause_local=args.pause_local)
        else:
            if not gpus:
                current = bindings(engine.config or {}).get(args.feature)
                gpus = [current.gpu_type] if current and current.gpu_type else ["L4"]
            plan = plan_remote(db, engine, args.feature, samples, gpus, concurrency, args.max_usd, args.experimental)
    except BenchmarkError as e:
        out(f"❌ {e}")
        for line in e.lines:
            out(f"   {line}")
        return 1
    finally:
        db.close()

    for line in describe(plan):
        out(line)
    if args.plan:
        out("Plan only: nothing was reserved or run.")
        return 0
    if not plan.remote and not args.here:
        argv_line = " ".join(f"--sample /bench/{Path(s.path).name}:{s.seconds:g}" for s in plan.samples)
        out("A local benchmark runs in a one-off container, never in a live worker. Put the samples in "
            "./tmp/bench and run:")
        out("  " + local_container_command(f"--engine {plan.slug} --feature {plan.feature} {argv_line} "
                                           f"--gpus {','.join(sorted({c.gpu for c in plan.combinations}))} "
                                           f"--concurrency {args.concurrency}"
                                           + (" --pause-local" if args.pause_local else "")
                                           + (" --apply" if args.apply else "")))
        return 0
    if plan.remote and not args.yes and not confirm(f"Spend up to US$ {plan.max_usd} on {plan.slug}? [y/N] "):
        out("Cancelled: nothing was reserved.")
        return 1

    paused = False
    try:
        if runner is None:
            runner = _default_runner(plan, engine, args)
        before_each = None
        if not plan.remote:
            if args.pause_local:
                paused = _pause_local(plan, session_factory, out)

            def before_each(combo, engine=engine):
                memory = gpu_memory()
                if memory is None:
                    raise BenchmarkError("No GPU visible in this container: run it with the GPU overlay "
                                         "(docker compose -f docker-compose.yml -f docker-compose.gpu.yml run ...)")
                for line in local_vram_guard(engine, plan.feature, combo.gpu, combo.e, memory["used_gb"],
                                             vision_model_id):
                    out("  VRAM " + line)
        results = run_plan(plan, runner, session_factory=session_factory, out=out, before_each=before_each)
    except BenchmarkError as e:
        out(f"❌ {e}")
        for line in e.lines:
            out(f"   {line}")
        return 1
    finally:
        if paused:
            _resume_local(plan, session_factory, out)

    out("")
    for line in table(results):
        out(line)
    fit = fit_vram(results)
    for gpu, f in fit.items():
        out(f"VRAM fit {gpu}: {f['base_gb']} + E x {f['per_exec_gb']} GB (x{VRAM_FIT_MARGIN} -> "
            f"{f['footprint_e1_gb']} GB per process)")
    if plan.contended:
        out("Results are `contended`: other work shared the card (use --pause-local for clean numbers).")
    best = recommend(plan, engine, results, fit, vision_model_id)
    if best is None:
        out("No recommendation: no combination finished within VRAM and min_speed.")
        return 0 if results else 1
    out(f"Recommended: {best['gpu']} E={best['executions_per_worker']} "
        f"({best['speed_aggregate']}x aggregate, US$ {best['usd_per_audio_hour']}/h of audio)")
    if args.apply:
        try:
            out("Applied: " + apply(plan, best, fit, session_factory=session_factory, vision_model_id=vision_model_id))
        except BenchmarkError as e:
            out(f"❌ {e}")
            for line in e.lines:
                out(f"   {line}")
            return 1
    return 0


def _default_runner(plan: Plan, engine: Engine, args):
    if not plan.remote:
        return run_local
    from workers.engines import remote

    adapter = remote.adapter_factory(engine, remote.open_credentials(engine))
    return ModalBenchRunner(engine, adapter, plan.feature, allow_unhashed=args.allow_unhashed)


def _pause_local(plan: Plan, session_factory, out, wait_seconds: int = 1800) -> bool:
    from shared.engines import store
    from shared.engines.store import in_flight

    db = ledger._session(session_factory)
    try:
        engine = db.get(Engine, plan.engine_id)
        if engine.status != "active":
            return False
        store.set_status(db, engine, "paused", version=None, actor_user_id=None, auth_method="cli")
        out("Local engine paused; waiting for its in-flight work (routed items only - unrouted audio still runs)")
        deadline = time.time() + wait_seconds
        while in_flight(db, plan.engine_id, plan.feature) and time.time() < deadline:
            db.expire_all()
            time.sleep(5)
        return True
    finally:
        db.close()


def _resume_local(plan: Plan, session_factory, out) -> None:
    from shared.engines import store

    db = ledger._session(session_factory)
    try:
        store.set_status(db, db.get(Engine, plan.engine_id), "active", version=None, actor_user_id=None,
                         auth_method="cli")
        out("Local engine active again.")
    finally:
        db.close()


if __name__ == "__main__":  # the local one-off container has no scripts/ directory
    from shared.engines.redact import install_log_redaction

    install_log_redaction()
    sys.exit(main())
