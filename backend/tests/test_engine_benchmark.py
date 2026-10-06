"""
Slice 4b of spec 0003: learned speed per (engine, feature, gpu, E) and the
benchmark command - no provider is ever contacted (fake runners, fake `modal run`
process), money goes through the same ledger and budget as any attempt.
"""

import json
import signal
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from shared.engines import pricing, speed
from shared.engines.capacity import Binding, bindings, deploy_state
from shared.models import Engine, EngineUsage
from tests.test_remote_engine import MODAL, TOKEN_ID, add_modal, world  # noqa: F401  (fixture)
from workers.engines import benchmark, sweeper
from workers.engines.modal_apps import bench_protocol

L4 = Binding(gpu_type="L4", workers=1, executions_per_worker=1)


def add_job_rows(world, n, *, media=600.0, exec_s=60.0, cold=5.0, actual="0.020000", engine_id=MODAL, gpu="L4",
                 start=0):
    base = datetime.utcnow() - timedelta(hours=1)
    with world.Session() as db:
        for i in range(start, start + n):
            at = base + timedelta(seconds=i)
            db.add(EngineUsage(kind="job", engine_id=engine_id, feature="transcription", subject_type="job",
                               subject_id=f"s-{engine_id}-{i}", attempt=1, period_start=at.date(), status="settled",
                               outcome="succeeded", gpu_type=gpu, executions_per_worker=1,
                               exec_started_at=at, exec_ended_at=at + timedelta(seconds=exec_s),
                               cold_start_seconds=Decimal(str(cold if i % 2 == 0 else 0)),
                               actual_usd=Decimal(actual), units={"media_seconds": media},
                               created_at=at, finished_at=at + timedelta(seconds=exec_s), heartbeat_at=at))
        db.commit()


# --- learned speed ------------------------------------------------------------------------------


def test_the_hold_is_the_worst_case_until_fifty_rows_then_the_learned_q95(world):
    add_modal(world)
    add_job_rows(world, 49)
    with world.Session() as db:
        stats = speed.compute(db, MODAL, "transcription", "L4", 1)
    assert stats.rows == 49 and not stats.learned and stats.source == "ledger"
    assert stats.s_p20 == pytest.approx(10.0) and stats.cold_s_p80 == pytest.approx(5.0)
    rate = pricing.rate_usd_per_s({}, L4)
    worst = pricing.round_up(Decimal(str(1980 / 10.0 + 15 + 5.0)) * rate * Decimal("1.2"))
    assert pricing.hold_usd({}, L4, 1980, stats) == worst

    add_job_rows(world, 1, start=49, actual="0.030000")
    with world.Session() as db:
        stats = speed.compute(db, MODAL, "transcription", "L4", 1)
    assert stats.rows == 50 and stats.learned
    q95 = Decimal(str(speed.quantile([0.02 / 600] * 49 + [0.03 / 600], 0.95))).quantize(Decimal("0.0000000001"))
    assert stats.usd_per_s_q95 == q95
    assert pricing.hold_usd({}, L4, 1980, stats) == pricing.round_up(Decimal("1980") * q95 * Decimal("1.2"))


def test_a_new_key_takes_its_benchmark_then_the_default_divided_by_e(world):
    add_modal(world)
    with world.Session() as db:
        stats = speed.compute(db, MODAL, "transcription", "L4", 1)
        assert stats.source == "default" and stats.s_p20 is None
        assert pricing.worst_case_speed({"default_speed": 12}, Binding(gpu_type="L4", workers=1,
                                                                        executions_per_worker=2), stats)[0] == 6.0
        db.add(EngineUsage(kind="benchmark", engine_id=MODAL, feature="transcription", period_start=datetime.utcnow().date(),
                           status="settled", outcome="succeeded", gpu_type="L4", executions_per_worker=1,
                           actual_usd=Decimal("0.01"), finished_at=datetime.utcnow(),
                           units={"result": {"speed_per_item_p20": 28.5, "cold_start_seconds": 3.0}}))
        db.commit()
        stats = speed.compute(db, MODAL, "transcription", "L4", 1)
    assert stats.source == "benchmark" and stats.s_p20 == 28.5 and stats.cold_s_p80 == 3.0


def test_speed_is_cached_per_key_for_an_hour_and_the_ledger_stays_the_source(world):
    add_modal(world)
    add_job_rows(world, 6)
    with world.Session() as db:
        stats = speed.get_stats(db, MODAL, "transcription", "L4", 1)
    key = f"engine:{MODAL}:transcription:L4:1:speed"
    client = world.redis.client
    assert client.exists(key) and 0 < client.ttl(key) <= 3600
    cached = speed.SpeedStats.from_cache(client.hgetall(key))
    assert cached.rows == stats.rows == 6 and cached.s_p20 == stats.s_p20
    client.flushall()  # losing Redis only means recomputing
    with world.Session() as db:
        assert speed.get_stats(db, MODAL, "transcription", "L4", 1).rows == 6
        assert [s.engine_id for s in speed.refresh_all(db, world.redis)].count(MODAL) == 1


def test_placement_reserves_the_learned_cost_once_the_key_has_fifty_rows(world):
    add_modal(world)
    add_job_rows(world, 60, actual="0.010000")
    world.set_route({"engine_ids": [MODAL]}, ["eng-local"])
    item = world.add_item(user="user-root", remote_allowed=True, media=1200)
    assert world.tick().placed == [(item, "modal_1", 1)]
    usage_id = world.item(item).usage_id
    expected = pricing.round_up(Decimal("1200") * Decimal(str(0.01 / 600)).quantize(Decimal("0.0000000001"))
                                * Decimal("1.2"))
    assert world.usage(usage_id).reserved_usd == expected
    assert expected < pricing.hold_usd({}, L4, 1200)  # cheaper than the cold worst case


# --- remote benchmark: plan, reservation, cap ---------------------------------------------------


def samples(tmp_path, *seconds):
    out = []
    for i, s in enumerate(seconds):
        path = tmp_path / f"s{i}.mp3"
        path.write_bytes(b"ID3")
        out.append(f"{path}:{s}")
    return benchmark.parse_samples(out)


def engine_row(world, engine_id=MODAL):
    with world.Session() as db:
        engine = db.get(Engine, engine_id)
        db.expunge(engine)
        return engine


def test_the_remote_plan_is_pessimistic_and_refuses_what_it_must_not_run(world, tmp_path):
    add_modal(world)
    engine = engine_row(world)
    sample = samples(tmp_path, 240)
    with world.Session() as db:
        plan = benchmark.plan_remote(db, engine, "transcription", sample, ["T4", "L4"], [1], Decimal("1.00"))
        rate = pricing.rate_usd_per_s({}, L4)
        l4 = plan.combinations[1]
        assert l4.estimate_usd == pricing.round_up(Decimal(str(30.0 + 60 + 240 / 10.0)) * rate)
        assert plan.total_usd == sum(c.estimate_usd for c in plan.combinations)
        assert sum(c.share_usd for c in plan.combinations) >= Decimal("1.00")
        assert l4.deadline_seconds == pytest.approx(float(l4.share_usd / rate))
        assert any("total (pessimistic)" in line for line in benchmark.describe(plan))

        with pytest.raises(benchmark.BenchmarkError, match="above --max-usd"):
            benchmark.plan_remote(db, engine, "transcription", sample, ["L4"], [1], Decimal("0.01"))
        with pytest.raises(benchmark.BenchmarkError, match="--experimental"):
            benchmark.plan_remote(db, engine, "transcription", sample, ["L4"], [1, 2], Decimal("1.00"))
        two = benchmark.plan_remote(db, engine, "transcription", sample, ["L4"], [2], Decimal("1.00"),
                                    experimental=True)
        assert two.combinations[0].terms["media_s"] == 480  # x E: the estimate assumes no gain
        engine.config = {**engine.config, "account_max_gpus": 1}
        with pytest.raises(benchmark.BenchmarkError, match="account_max_gpus"):
            benchmark.plan_remote(db, engine, "transcription", sample, ["L4"], [1], Decimal("1.00"))


def fake_runner(billed=100.0, items=2, completed=True):
    calls = []

    def run(combo, samples_, heartbeat):
        calls.append((combo.gpu, combo.e))
        heartbeat()
        return benchmark.RunResult(completed, billed, 50.0,
                                   [benchmark.ItemTiming(240.0, 10.0, 3.0 if i == 0 else 0.0, 12.0)
                                    for i in range(items)])
    run.calls = calls
    return run


def test_a_remote_benchmark_reserves_its_cap_settles_measured_cost_and_feeds_the_key(world, tmp_path):
    add_modal(world)
    engine = engine_row(world)
    with world.Session() as db:
        plan = benchmark.plan_remote(db, engine, "transcription", samples(tmp_path, 240), ["T4", "L4"], [1],
                                     Decimal("1.00"))
    runner = fake_runner(billed=100.0)
    results = benchmark.run_plan(plan, runner, session_factory=world.Session, out=lambda line: None)
    assert runner.calls == [("T4", 1), ("L4", 1)]
    with world.Session() as db:
        rows = db.query(EngineUsage).filter(EngineUsage.kind == "benchmark").order_by(EngineUsage.id).all()
        assert [(r.placed_by, r.status, r.outcome, r.gpu_type) for r in rows] == \
            [("cli", "settled", "succeeded", "T4"), ("cli", "settled", "succeeded", "L4")]
        assert sum(r.reserved_usd for r in rows) >= Decimal("1.00")
        l4 = rows[1]
        assert l4.actual_usd == pricing.round_up(Decimal("100") * pricing.rate_usd_per_s({}, L4))
        assert l4.units["result"]["speed_per_item"] == 24.0 and l4.units["result"]["speed_aggregate"] == 9.6
        assert db.query(EngineUsage).filter(EngineUsage.kind == "job").count() == 0  # never a production slot
        stats = speed.compute(db, MODAL, "transcription", "L4", 1)
    assert stats.source == "benchmark" and stats.s_p20 == 24.0
    assert results[1]["usd_per_audio_hour"] == str((pricing.rate_usd_per_s({}, L4) * 3600 / Decimal("9.6"))
                                                   .quantize(Decimal("0.0001")))


def test_the_benchmark_stops_before_a_combination_that_would_pass_the_cap(world, tmp_path):
    add_modal(world)
    engine = engine_row(world)
    with world.Session() as db:
        plan = benchmark.plan_remote(db, engine, "transcription", samples(tmp_path, 240), ["L4", "A10G"], [1],
                                     Decimal("0.50"))
    out = []
    runner = fake_runner(billed=1800.0, completed=False)  # cut late: the interrupt took long
    benchmark.run_plan(plan, runner, session_factory=world.Session, out=out.append)
    assert runner.calls == [("L4", 1)]
    assert any(line.startswith("Stopping") for line in out)
    with world.Session() as db:
        statuses = [r.status for r in db.query(EngineUsage).filter(EngineUsage.kind == "benchmark")
                    .order_by(EngineUsage.id)]
    assert statuses == ["settled", "released"]


def test_a_benchmark_never_reserves_past_the_accounts_budget(world, tmp_path):
    add_modal(world, limit_usd="1.20")  # 0.70 left after min_remaining 0.50
    engine = engine_row(world)
    with world.Session() as db:
        plan = benchmark.plan_remote(db, engine, "transcription", samples(tmp_path, 120), ["L4"], [1],
                                     Decimal("1.00"))
    with pytest.raises(benchmark.BenchmarkError, match="lower --max-usd"):
        benchmark.run_plan(plan, fake_runner(), session_factory=world.Session, out=lambda line: None)
    assert world.count(EngineUsage, kind="benchmark") == 0


def test_the_command_asks_before_spending_and_apply_needs_a_redeploy(world, tmp_path, monkeypatch):
    add_modal(world)
    sample = str(tmp_path / "a.mp3")
    (tmp_path / "a.mp3").write_bytes(b"ID3")
    out = []
    argv = ["--engine", "modal_1", "--sample", f"{sample}:240", "--gpus", "L4", "--max-usd", "0.30"]
    assert benchmark.main(argv, session_factory=world.Session, out=out.append, confirm=lambda q: False,
                          runner=fake_runner()) == 1
    assert world.count(EngineUsage, kind="benchmark") == 0 and "Cancelled" in out[-1]

    assert benchmark.main(argv + ["--plan"], session_factory=world.Session, out=out.append) == 0
    assert world.count(EngineUsage, kind="benchmark") == 0

    out.clear()
    assert benchmark.main(argv + ["--gpus", "T4,L4", "--yes", "--apply"], session_factory=world.Session,
                          out=out.append, runner=fake_runner()) == 0
    assert any(line.startswith("Recommended: T4 E=1") for line in out)  # same speed, cheaper GPU
    engine = engine_row(world)
    binding = bindings(engine.config)["transcription"]
    assert binding.gpu_type == "T4"
    assert deploy_state("modal", engine.deployments, "transcription", binding) == "needs_redeploy"


# --- the ephemeral app subprocess -----------------------------------------------------------------


class FakeProcess:
    def __init__(self, lines, finishes=True):
        self._lines = list(lines)
        self.finishes = finishes
        self.signals = []
        self.killed = False
        self.stdout = self
        self.returncode = None

    def readline(self):
        return self._lines.pop(0) if self._lines else ""

    def poll(self):
        if self.finishes and not self._lines:
            self.returncode = 0
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self.returncode = -2

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True


class Ticker:
    def __init__(self, step=10.0):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def test_each_combination_is_an_ephemeral_modal_run_with_a_scratch_environment(world, tmp_path):
    add_modal(world)
    engine = engine_row(world)
    combo = benchmark.Combination("L4", 1, rate=pricing.rate_usd_per_s({}, L4), deadline_seconds=500.0)
    seen = {}
    done = bench_protocol.done_line(1000.0, 1100.0, 80.0, [{"media_seconds": 240, "exec_seconds": 8,
                                                           "cold_start_seconds": 3, "wall_seconds": 12}])

    def popen(command, env, cwd, **kwargs):
        seen.update(command=command, env=env)
        return FakeProcess([bench_protocol.started_line(1000.0) + "\n", done + "\n"])

    adapter = SimpleNamespace(subprocess_env=lambda home, extra: {"MODAL_TOKEN_ID": TOKEN_ID, "HOME": home, **extra})
    runner = benchmark.ModalBenchRunner(engine, adapter, popen=popen, clock=Ticker(), sleep=lambda s: None)
    result = runner(combo, samples(tmp_path, 240), heartbeat=lambda: None)
    assert seen["command"][1:] == ["-m", "modal", "run", "-m", "workers.engines.modal_apps.bench_entry::bench"]
    assert "deploy" not in seen["command"] and TOKEN_ID not in " ".join(seen["command"])
    spec = json.loads(seen["env"]["INGESTIFY_MODAL_DEPLOY"])
    assert spec["decorator"]["gpu"] == "L4" and spec["decorator"]["max_containers"] == 1
    assert json.loads(seen["env"][bench_protocol.BENCH_ENV])["executions"] == 1
    assert result.completed and result.billed_seconds == 100.0 and result.items[0].exec_seconds == 8


def test_whisperx_benchmark_uses_full_pipeline_and_deployment_models(world, tmp_path, monkeypatch):
    from shared.config import get_settings
    add_modal(world)
    engine = engine_row(world)
    manifest = {'qualified':True, 'asr':{'model':'turbo','revision':'a'*40},
                'vad':{'revision':'b'*40}, 'aligners':{'pt':{'revision':'c'*40}},
                'diarizer':{'model':'pyannote/speaker-diarization-community-1','revision':'d'*40}}
    engine.config = {**engine.config, 'whisperx_manifest':manifest}
    monkeypatch.setattr(get_settings(), 'whisperx_model_dir', '/models/test-whisperx')
    adapter = SimpleNamespace(subprocess_env=lambda home, extra:extra)
    runner = benchmark.ModalBenchRunner(engine, adapter)
    env = runner.env(str(tmp_path), benchmark.Combination('L4', 1), [])
    options = json.loads(env[bench_protocol.BENCH_ENV])['options']
    assert env['WHISPERX_MODEL_DIR'] == '/models/test-whisperx'
    assert options['transcriber_provider'] == 'whisperx'
    assert options['diarize'] is True and options['include_word_timestamps'] is True
    assert options['transcription_profile']['models']['asr_revision'] == 'a'*40
    assert options['transcription_profile']['models']['diarizer_revision'] == 'd'*40


def test_local_whisperx_benchmark_does_not_measure_asr_only_when_default_is_opt_in(monkeypatch):
    from shared.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'audio_transcriber_provider', 'whisperx')
    monkeypatch.setattr(settings, 'whisperx_diarization_default', False)
    options = benchmark.qualification_options(settings)
    assert options['diarize'] is True
    assert options['transcription_profile']['diarize'] is True


def test_modal_entry_sends_benchmark_provider_options(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path
    from workers.engines.modal_apps import protocol
    media = tmp_path / 'sample.mp3'
    media.write_bytes(b'fixture')
    options = {'transcriber_provider':'whisperx', 'diarize':True, 'include_word_timestamps':True}
    monkeypatch.setenv(bench_protocol.BENCH_ENV, json.dumps({'samples':[str(media)], 'options':options}))
    received = []
    class StopAfterRequest(Exception):
        pass
    def spawn(request):
        received.append(protocol.parse_request(request)['options'])
        raise StopAfterRequest()
    fake_app = SimpleNamespace(local_entrypoint=lambda:lambda fn:fn)
    fake_runner = lambda:SimpleNamespace(transcribe=SimpleNamespace(spawn=spawn))
    monkeypatch.setitem(sys.modules, 'workers.engines.modal_apps.whisper_app',
                        SimpleNamespace(app=fake_app, WhisperRunner=fake_runner))
    path = Path(benchmark.__file__).parent / 'modal_apps/bench_entry.py'
    spec = importlib.util.spec_from_file_location('benchmark_entry_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(StopAfterRequest):
        module.bench()
    assert received[0]['transcriber_provider'] == 'whisperx' and received[0]['diarize'] is True


def test_a_combination_past_its_deadline_is_interrupted_and_billed_from_the_app_start(world, tmp_path):
    add_modal(world)
    engine = engine_row(world)
    combo = benchmark.Combination("L4", 1, rate=pricing.rate_usd_per_s({}, L4), deadline_seconds=50.0)
    process = FakeProcess([bench_protocol.started_line(1000.0) + "\n"], finishes=False)
    adapter = SimpleNamespace(subprocess_env=lambda home, extra: {"HOME": home, **extra})
    runner = benchmark.ModalBenchRunner(engine, adapter, popen=lambda *a, **k: process, clock=Ticker(10.0),
                                        sleep=lambda s: None)
    result = runner(combo, samples(tmp_path, 240), heartbeat=lambda: None)
    assert process.signals == [signal.SIGINT]
    assert not result.completed and result.error is None
    assert 50.0 < result.billed_seconds <= 50.0 + 3 * 10.0  # the deadline plus the polling latency


def test_bench_output_is_parsed_strictly():
    assert bench_protocol.parse_output("noise\n" + bench_protocol.started_line(1.0)) is None
    good = bench_protocol.done_line(1.0, 9.0, 5.0, [{"media_seconds": 60, "exec_seconds": 2}])
    assert bench_protocol.parse_output("x\n" + good)["items"][0]["cold_start_seconds"] == 0.0
    assert bench_protocol.parse_output(bench_protocol.PREFIX + '{"event": "done", "items": [1]}') is None


def test_a_benchmark_whose_cli_died_is_settled_lost_by_the_sweeper(world, tmp_path):
    add_modal(world)
    engine = engine_row(world)
    with world.Session() as db:
        plan = benchmark.plan_remote(db, engine, "transcription", samples(tmp_path, 60), ["L4"], [1], Decimal("0.20"))
    benchmark.reserve(plan, "benchmark:dead", session_factory=world.Session, now=datetime.utcnow() - timedelta(hours=1))
    counts = sweeper.sweep(celery=world.celery, session_factory=world.Session, redis_client=world.redis)
    usage = world.usage(plan.combinations[0].usage_id)
    assert counts["benchmarks_lost"] == 1 and usage.outcome == "lost" and usage.actual_usd == usage.reserved_usd


# --- local benchmark --------------------------------------------------------------------------------


def test_a_local_benchmark_runs_only_in_a_one_off_container(world, tmp_path):
    sample = tmp_path / "a.mp3"
    sample.write_bytes(b"ID3")
    out = []
    assert benchmark.main(["--engine", "local", "--sample", f"{sample}:240", "--concurrency", "1,2"],
                          session_factory=world.Session, out=out.append) == 0
    command = out[-1]
    assert "run --rm --no-deps" in command and "worker-audio python -m workers.engines.benchmark" in command
    assert command.rstrip().endswith("--here") and "--concurrency 1,2" in command
    assert world.count(EngineUsage, kind="benchmark") == 0


def test_the_local_vram_guard_counts_what_is_resident():
    engine = SimpleNamespace(config={"gpus": [{"ref": "gpu0", "vram_gb": 16, "vram_reserve_gb": 1.0}],
                                     "features": {"transcription": {"gpu_ref": "gpu0", "workers": 2}}})
    assert "fits" in benchmark.local_vram_guard(engine, "transcription", "gpu0", 2, 8.0)[0]
    with pytest.raises(benchmark.BenchmarkError) as refused:
        benchmark.local_vram_guard(engine, "transcription", "gpu0", 3, 8.0)
    assert refused.value.lines == ["gpu0: used now 8.00 + 3 x 3 (transcription) + reserve 1 = 18.00 GB of 16 GB"
                                   " - does NOT fit"]


def test_a_local_benchmark_measures_vram_fits_it_and_applies_replicas_and_footprint(world, tmp_path, monkeypatch):
    sample = tmp_path / "a.mp3"
    sample.write_bytes(b"ID3")
    monkeypatch.setattr(benchmark, "gpu_memory", lambda: {"total_gb": 16.0, "used_gb": 4.0, "uuid": "GPU-1"})

    def runner(combo, samples_, heartbeat):
        e = combo.e
        return benchmark.RunResult(True, 100.0, 60.0 if e == 1 else 70.0,
                                   [benchmark.ItemTiming(240.0, 15.0 * e, 2.0, 15.0 * e)] * e,
                                   vram_baseline_gb=4.0, vram_peak_gb=4.0 + 0.4 + 2.4 * e)
    out = []
    assert benchmark.main(["--engine", "local", "--sample", f"{sample}:240", "--concurrency", "1,2", "--here",
                           "--apply"], session_factory=world.Session, out=out.append, runner=runner) == 0
    assert any("VRAM gpu0: used now 4.00 + 2 x 3" in line for line in out)
    assert any("VRAM fit gpu0: 0.4 + E x 2.4 GB" in line for line in out)
    assert any("contended" in line for line in out)
    with world.Session() as db:
        rows = db.query(EngineUsage).filter(EngineUsage.kind == "benchmark").all()
        assert len(rows) == 2 and all(r.actual_usd == 0 and r.units["contended"] for r in rows)
        binding = bindings(db.get(Engine, "eng-local").config)["transcription"]
    assert binding.workers == 2 and binding.executions_per_worker == 1  # 2 x 240 s in 70 s beats 240 s in 60 s
    assert binding.vram_override_gb == 3.08  # (0.4 + 2.4) x 1.1
