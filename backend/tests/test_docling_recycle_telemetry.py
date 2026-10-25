"""Why a Docling pool child exited, and the children that vanished without a shutdown."""
import asyncio
import logging
import os
import subprocess
from types import SimpleNamespace

import pytest

import workers.celery_app  # noqa: F401  (connects the pool signals)
from api import admin_routes
from celery.signals import worker_init, worker_process_shutdown
from shared import docling_coldstart as cs


@pytest.fixture
def sibling():
    """A live process other than this one (pytest can be pid 1 in a container)."""
    proc = subprocess.Popen(["sleep", "30"])
    yield proc.pid
    proc.kill()
    proc.wait()


@pytest.fixture(autouse=True)
def limits(monkeypatch, tmp_path):
    monkeypatch.setattr(cs, "_limits", {"max_memory_kb": 5_000_000, "max_tasks": None})
    monkeypatch.setattr(cs, "CGROUP_ROOT", str(tmp_path))  # no cgroup files unless a test writes them
    monkeypatch.setattr(cs, "peak_rss_kb", lambda: 5_012_345)
    monkeypatch.setattr(cs, "current_rss_kb", lambda: 4_000_000)


def _hash(client):
    return client.hgetall(cs.key_for(cs.hour_bucket(), cs.hostname()))


def _registry(client):
    return client.hgetall(cs._children_key())


@pytest.fixture
def spy_pipeline(_docling_telemetry_fake_redis, monkeypatch):
    """spy_pipeline(on_read): run on_read(key) after each WATCHed registry read (another child in between)."""
    client = _docling_telemetry_fake_redis
    real_pipeline = client.pipeline

    def install(on_read):
        class Spy:
            def __init__(self, pipe):
                self._pipe = pipe

            def __enter__(self):
                self._pipe.__enter__()
                return self

            def __exit__(self, *exc):
                return self._pipe.__exit__(*exc)

            def __getattr__(self, name):
                return getattr(self._pipe, name)

            def hgetall(self, key):
                data = self._pipe.hgetall(key)
                on_read(key)
                return data

        monkeypatch.setattr(client, "pipeline", lambda *a, **k: Spy(real_pipeline(*a, **k)))

    return install


@pytest.mark.parametrize("args,expected", [
    ((155, 5_100_000, 5_000_000, None), "memory_limit"),
    ((155, 4_000_000, 5_000_000, 50), "max_tasks"),
    ((155, 4_000_000, None, None), "unknown"),
    ((0, 1, 5_000_000, None), "shutdown"),
    ((-241, 1, 5_000_000, None), "shutdown"),
    ((1, 1, 5_000_000, None), "unknown"),
    ((None, 1, 5_000_000, None), "unknown"),
])
def test_classify_exit(args, expected):
    assert cs.classify_exit(*args) == expected


def test_shutdown_reason_and_log(_docling_telemetry_fake_redis, caplog):
    with caplog.at_level(logging.INFO):
        cs.record_process_shutdown(155)
    data = _hash(_docling_telemetry_fake_redis)
    assert data["recycle:memory_limit"] == "1"
    assert (data["last_exitcode"], data["max_memory_per_child_kb"]) == ("155", "5000000")
    assert "exitcode=155 reason=memory_limit" in caplog.text and "peak_pct_of_limit=100.2" in caplog.text
    cs.record_process_shutdown()  # no exitcode (old callers): counted, reason unknown
    data = _hash(_docling_telemetry_fake_redis)
    assert data["processes_stopped"] == "2" and data["recycle:unknown"] == "1"
    assert data["last_exitcode"] == "155"


def test_start_registers_own_pid_with_ttl(_docling_telemetry_fake_redis):
    cs.record_process_start()
    assert _registry(_docling_telemetry_fake_redis) == {str(os.getpid()): cs._proc_start_time(os.getpid())}
    assert 0 < _docling_telemetry_fake_redis.ttl(cs._children_key()) <= cs.COLDSTART_TTL_SECONDS
    assert _hash(_docling_telemetry_fake_redis)["processes_started"] == "1"


def test_dead_pid_counts_once_and_is_removed(_docling_telemetry_fake_redis, caplog):
    _docling_telemetry_fake_redis.hset(cs._children_key(), "999999", "123")
    with caplog.at_level(logging.WARNING):
        cs.record_process_start()
    assert _hash(_docling_telemetry_fake_redis)["processes_vanished"] == "1"
    assert "999999" not in _registry(_docling_telemetry_fake_redis)
    assert "docling.process_vanished count=1 pids=999999" in caplog.text
    cs.record_process_start()  # the entry is gone: no second claim
    assert _hash(_docling_telemetry_fake_redis)["processes_vanished"] == "1"


@pytest.mark.parametrize("who,starttime,vanished", [
    ("own", "-1", True),       # same hostname and pid after a container restart
    ("sibling", "real", False),  # live sibling
    ("sibling", "-1", True),   # pid reused by another process
])
def test_existing_entry_for_a_live_pid(_docling_telemetry_fake_redis, sibling, who, starttime, vanished):
    pid = os.getpid() if who == "own" else sibling
    _docling_telemetry_fake_redis.hset(
        cs._children_key(), str(pid), cs._proc_start_time(pid) if starttime == "real" else starttime)
    cs.record_process_start()
    data = _hash(_docling_telemetry_fake_redis)
    assert data.get("processes_vanished") == ("1" if vanished else None)
    assert str(os.getpid()) in _registry(_docling_telemetry_fake_redis)


def test_concurrent_children_claim_a_stale_entry_once(_docling_telemetry_fake_redis, monkeypatch, sibling, spy_pipeline):
    """B claims and registers between A's read and A's execute: A must not count it again."""
    client = _docling_telemetry_fake_redis
    client.hset(cs._children_key(), "999999", "123")
    armed = [True]

    def child_b(_key):
        if armed and not armed.clear():
            with monkeypatch.context() as m:
                m.setattr(cs.os, "getpid", lambda: sibling)
                cs.record_process_start()

    spy_pipeline(child_b)
    cs.record_process_start()  # child A
    assert _hash(client)["processes_vanished"] == "1"
    assert set(_registry(client)) == {str(os.getpid()), str(sibling)}


def test_registration_survives_a_lost_cleanup(_docling_telemetry_fake_redis, spy_pipeline):
    """Every WATCH attempt loses: no vanished count, but the child is registered."""
    client = _docling_telemetry_fake_redis
    client.hset(cs._children_key(), "999999", "123")
    spy_pipeline(lambda key: (client.hset(key, "424242", "1"), client.hdel(key, "424242")))  # touch the key
    cs.record_process_start()
    data = _hash(client)
    assert data["processes_started"] == "1" and "processes_vanished" not in data
    assert str(os.getpid()) in _registry(client)
    assert client.ttl(cs._children_key()) > 0


def test_clean_shutdown_clears_registry(_docling_telemetry_fake_redis):
    cs.record_process_start()
    cs.record_process_shutdown(0)
    assert _registry(_docling_telemetry_fake_redis) == {}
    cs.record_process_start()
    data = _hash(_docling_telemetry_fake_redis)
    assert data["recycle:shutdown"] == "1" and "processes_vanished" not in data


def test_cgroup_fields(_docling_telemetry_fake_redis, tmp_path):
    cs.record_process_shutdown(155)
    assert not any(k.startswith("cgroup_") for k in _hash(_docling_telemetry_fake_redis))  # no files: no fields

    (tmp_path / "memory.events").write_text("low 0\nhigh 0\nmax 0\noom 3\noom_kill 3\n")
    (tmp_path / "memory.peak").write_text("6144000\n")
    (tmp_path / "memory.max").write_text("max\n")
    cs.record_process_start()
    cs.record_process_shutdown(0)
    data = _hash(_docling_telemetry_fake_redis)
    assert (data["cgroup_oom_kill"], data["cgroup_memory_peak_kb"]) == ("3", "6000")
    assert "cgroup_memory_max_kb" not in data  # "max" means unlimited

    (tmp_path / "memory.max").write_text("6442450944\n")
    cs.record_process_shutdown(0)
    assert _hash(_docling_telemetry_fake_redis)["cgroup_memory_max_kb"] == "6291456"


def test_signals_record_limits_and_reason(_docling_telemetry_fake_redis, monkeypatch):
    monkeypatch.setattr(cs, "_limits", {"max_memory_kb": None, "max_tasks": None})

    class Controller:  # signal senders must be hashable
        max_memory_per_child, max_tasks_per_child = 5_000_000, None

    worker_init.send(sender=Controller())
    assert cs._limits == {"max_memory_kb": 5_000_000, "max_tasks": None}
    worker_process_shutdown.send(sender=None, pid=1, exitcode=155)
    assert _hash(_docling_telemetry_fake_redis)["recycle:memory_limit"] == "1"


def test_read_hours_defaults_and_values(_docling_telemetry_fake_redis):
    client = _docling_telemetry_fake_redis
    client.hset(cs.key_for(cs.hour_bucket(), "old"), mapping={"cold:process_start": 1, "conversions": 1})
    cs.record_process_shutdown(155)
    rows = {r["worker"]: r for r in cs.read_hours(1)}
    old = rows["old"]
    assert [old[f"recycle_{r}"] for r in cs.RECYCLE_REASONS] == [0, 0, 0, 0]
    assert old["processes_vanished"] == 0 and old["peak_rss_pct_of_limit"] is None and old["last_exitcode"] is None
    new = rows[cs.hostname()]
    assert new["recycle_memory_limit"] == 1
    assert (new["last_exitcode"], new["peak_rss_pct_of_limit"]) == (155, 100.2)


def test_endpoint_shows_recycle_fields(_docling_telemetry_fake_redis):
    _docling_telemetry_fake_redis.hset(cs.key_for(cs.hour_bucket(), "old"), mapping={"cold:process_start": 1, "conversions": 1})
    cs.record_process_shutdown(155)
    rows = {r["worker"]: r for r in asyncio.run(admin_routes.docling_cold_starts(admin_user=None)).model_dump()["rows"]}
    old, new = rows["old"], rows[cs.hostname()]
    assert old["recycle_memory_limit"] == 0 and old["last_exitcode"] is None and old["peak_rss_pct_of_limit"] is None
    assert (new["recycle_memory_limit"], new["last_exitcode"], new["peak_rss_pct_of_limit"]) == (1, 155, 100.2)


def test_redis_outage_never_raises_and_trips_breaker(monkeypatch):
    calls = []

    class Down:
        def hgetall(self, *_):
            calls.append(1)
            raise ConnectionError("down")

        def pipeline(self):
            calls.append(1)
            raise ConnectionError("down")

    monkeypatch.setattr(cs, "_redis", lambda: Down())
    monkeypatch.setattr(cs, "_skip_until", 0.0)
    cs.record_process_start()
    cs.record_process_shutdown(155)
    cs.record_process_start()
    assert len(calls) == 1 and cs._skip_until > 0


def test_conversion_renews_and_recreates_registry_entry(_docling_telemetry_fake_redis):
    client = _docling_telemetry_fake_redis
    cs.record_process_start()
    client.expire(cs._children_key(), 100)
    cs.record_conversion(SimpleNamespace(), 1.0, None, "pdf", probe=True)
    assert client.ttl(cs._children_key()) <= 100  # a probe touches nothing
    cs.record_conversion(SimpleNamespace(), 1.0, None, "pdf")
    assert client.ttl(cs._children_key()) > 100
    client.delete(cs._children_key())  # idle for 48 h, or evicted
    cs.record_conversion(SimpleNamespace(), 1.0, None, "pdf")
    assert _registry(client) == {str(os.getpid()): cs._proc_start_time(os.getpid())}
    assert client.ttl(cs._children_key()) > 0
