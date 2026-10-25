"""Why a Docling pool child exited, and the children that vanished without a shutdown."""
import logging
import os
import subprocess

import pytest

import workers.celery_app  # noqa: F401  (connects the pool signals)
from celery.signals import worker_init, worker_process_shutdown
from shared import docling_coldstart as cs


@pytest.fixture
def sibling():
    """A live process that is not this one (pytest can be pid 1 in a container)."""
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
    assert "max_tasks_per_child" not in data
    assert "exitcode=155 reason=memory_limit" in caplog.text and "peak_pct_of_limit=100.2" in caplog.text


def test_shutdown_without_exitcode_keeps_old_contract(_docling_telemetry_fake_redis):
    cs.record_process_shutdown()
    data = _hash(_docling_telemetry_fake_redis)
    assert data["processes_stopped"] == "1" and data["recycle:unknown"] == "1"
    assert "last_exitcode" not in data


def test_start_registers_own_pid(_docling_telemetry_fake_redis):
    cs.record_process_start()
    assert _registry(_docling_telemetry_fake_redis) == {str(os.getpid()): cs._proc_start_time(os.getpid())}
    assert _hash(_docling_telemetry_fake_redis)["processes_started"] == "1"
    assert "processes_vanished" not in _hash(_docling_telemetry_fake_redis)


def test_dead_pid_counts_once_and_is_removed(_docling_telemetry_fake_redis, caplog):
    _docling_telemetry_fake_redis.hset(cs._children_key(), "999999", "123")
    with caplog.at_level(logging.WARNING):
        cs.record_process_start()
    assert _hash(_docling_telemetry_fake_redis)["processes_vanished"] == "1"
    assert "999999" not in _registry(_docling_telemetry_fake_redis)
    assert "docling.process_vanished count=1 pids=999999" in caplog.text
    cs.record_process_start()  # the entry is gone: no second claim
    assert _hash(_docling_telemetry_fake_redis)["processes_vanished"] == "1"


def test_live_sibling_is_not_counted(_docling_telemetry_fake_redis, sibling):
    _docling_telemetry_fake_redis.hset(cs._children_key(), str(sibling), cs._proc_start_time(sibling))
    cs.record_process_start()
    assert "processes_vanished" not in _hash(_docling_telemetry_fake_redis)
    assert str(sibling) in _registry(_docling_telemetry_fake_redis)


def test_reused_pid_counts(_docling_telemetry_fake_redis, sibling):
    _docling_telemetry_fake_redis.hset(cs._children_key(), str(sibling), "-1")  # alive, other starttime
    cs.record_process_start()
    assert _hash(_docling_telemetry_fake_redis)["processes_vanished"] == "1"


def test_only_the_hdel_that_removed_counts(_docling_telemetry_fake_redis, monkeypatch):
    """Another child deletes the entry between our HGETALL and our HDEL."""
    client = _docling_telemetry_fake_redis
    client.hset(cs._children_key(), "999999", "123")
    real = client.hgetall

    def racing(key):
        data = real(key)
        client.hdel(key, "999999")
        return data

    monkeypatch.setattr(client, "hgetall", racing)
    cs.record_process_start()
    assert "processes_vanished" not in _hash(client)


def test_clean_shutdown_clears_registry(_docling_telemetry_fake_redis):
    cs.record_process_start()
    cs.record_process_shutdown(0)
    assert _registry(_docling_telemetry_fake_redis) == {}
    cs.record_process_start()
    data = _hash(_docling_telemetry_fake_redis)
    assert data["recycle:shutdown"] == "1" and "processes_vanished" not in data


def test_cgroup_fields(_docling_telemetry_fake_redis, tmp_path):
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


def test_missing_cgroup_files_leave_fields_out(_docling_telemetry_fake_redis):
    cs.record_process_start()
    cs.record_process_shutdown(155)
    data = _hash(_docling_telemetry_fake_redis)
    assert not any(k.startswith("cgroup_") for k in data)


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
    assert old["recycle_by_reason"] == {"memory_limit": 0, "max_tasks": 0, "shutdown": 0, "unknown": 0}
    assert old["processes_vanished"] == 0 and old["peak_rss_pct_of_limit"] is None and old["last_exitcode"] is None
    new = rows[cs.hostname()]
    assert new["recycle_by_reason"]["memory_limit"] == 1
    assert (new["last_exitcode"], new["peak_rss_pct_of_limit"]) == (155, 100.2)


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
