"""Docling cold-start telemetry: classification, Redis aggregate, admin endpoint, warning."""
import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis
import pytest

import workers.celery_app  # noqa: F401  (import order used by the worker)
import workers.converter as converter_module
from api import admin_routes
from shared import docling_coldstart as cs
from shared.config import get_settings
from workers import monitoring
from workers.converter import get_converter


@pytest.fixture
def redis_client(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cs, "_redis", lambda: client)
    monkeypatch.setattr(cs, "_redis_read", lambda: client)
    return client


@pytest.fixture(autouse=True)
def fake_docling(monkeypatch):
    class Fake:
        def __init__(self, **options):
            self.options = options

    monkeypatch.setattr(converter_module, "DoclingConverter", Fake)
    converter_module._cached_converter.cache_clear()
    get_settings.cache_clear()
    yield
    converter_module._cached_converter.cache_clear()
    get_settings.cache_clear()


def _reasons(redis_client):
    key = cs.key_for(cs.hour_bucket(), cs.hostname())
    data = redis_client.hgetall(key)
    return {r: int(data.get(f"cold:{r}", 0)) for r in cs.REASONS}, key


def test_reason_classification(redis_client, monkeypatch):
    monkeypatch.setenv("DOCLING_CONVERTER_CACHE_SIZE", "2")
    get_settings.cache_clear()
    get_converter("fast")       # process_start
    get_converter("balanced")   # new_options (cache not full)
    get_converter("quality")    # new_options; evicts fast
    get_converter("fast")       # evicted: seen in this process, expelled by the LRU
    get_converter("fast")       # hit: no build

    counts, key = _reasons(redis_client)
    assert counts == {"process_start": 1, "new_options": 2, "evicted": 1}
    assert int(redis_client.hget(key, "conversions")) == 5
    assert redis_client.ttl(key) > 47 * 3600


def test_cache_size_comes_from_the_setting(redis_client, monkeypatch):
    assert get_settings().docling_converter_cache_size == 3
    get_converter("fast"); get_converter("balanced"); get_converter("quality")
    assert get_converter("fast") is get_converter("fast")
    assert _reasons(redis_client)[0]["evicted"] == 0  # three slots: nothing evicted


def test_cold_start_log_line(redis_client, caplog):
    with caplog.at_level(logging.INFO, logger="shared.docling_coldstart"):
        get_converter("fast")
    line = next(r.getMessage() for r in caplog.records if "docling.cold_start" in r.getMessage())
    assert "reason=process_start" in line and "seconds=" in line and "pid=" in line
    assert "hostname=" in line and "cache_size=3" in line


def test_redis_down_never_breaks_a_conversion(monkeypatch):
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(cs, "_redis", boom)
    assert get_converter("fast") is not None
    cs.record_process_start()
    cs.record_process_shutdown()


def test_process_counters_and_rss(redis_client, monkeypatch):
    monkeypatch.setattr(cs, "current_rss_kb", lambda: 2_450_000)
    monkeypatch.setattr(cs, "peak_rss_kb", lambda: 2_600_000)
    cs.record_process_start()
    cs.record_process_start()
    cs.record_process_shutdown()
    key = cs.key_for(cs.hour_bucket(), cs.hostname())
    assert redis_client.hget(key, "processes_started") == "2"
    assert redis_client.hget(key, "processes_stopped") == "1"
    assert redis_client.hget(key, "rss_kb_max") == "2450000"
    assert redis_client.hget(key, "peak_rss_kb") == "2600000"


def test_read_hours_aggregates_per_hour_and_worker(redis_client):
    now = datetime(2026, 10, 24, 12, 30, tzinfo=timezone.utc)
    key = cs.key_for("2026102412", "w1")
    redis_client.hset(key, mapping={"cold:process_start": 2, "cold:evicted": 1, "seconds:process_start": "20.5",
                                    "seconds:evicted": "9.5", "processes_started": 2, "conversions": 60})
    redis_client.hset(cs.key_for("2026102411", "w2"), mapping={"cold:new_options": 1, "seconds:new_options": "3"})
    rows = cs.read_hours(24, now=now, client=redis_client)

    assert [(r["hour"][:13], r["worker"]) for r in rows] == [("2026-10-24T11", "w2"), ("2026-10-24T12", "w1")]
    w1 = rows[1]
    assert w1["cold_starts"] == 3 and w1["seconds_total"] == 30.0
    assert w1["by_reason"] == {"process_start": 2, "new_options": 0, "evicted": 1}
    assert w1["cold_starts_per_100_conversions"] == 5.0
    assert rows[0]["cold_starts_per_100_conversions"] is None
    # a row written before the per-convert() counters existed reads back with defaults
    assert (rows[0]["conversions_first"], rows[0]["pages_ok"], rows[0]["docling_version"]) == (0, 0, None)


def test_admin_endpoint_shape_and_auth(redis_client, monkeypatch):
    redis_client.hset(cs.key_for(cs.hour_bucket(), "w1"), mapping={"cold:process_start": 1, "seconds:process_start": "10"})
    out = asyncio.run(admin_routes.docling_cold_starts(admin_user=SimpleNamespace(id="x")))
    dumped = out.model_dump()
    assert dumped["hours"] == 24 and dumped["warn_per_hour"] == 6
    assert dumped["rows"][0]["worker"] == "w1"
    assert dumped["rows"][0]["by_reason"]["process_start"] == 1

    route = next(r for r in admin_routes.router.routes if r.path == "/admin/docling/cold-starts")
    assert route.response_model is admin_routes.DoclingColdStartsResponse
    dependants = [d.call for d in route.dependant.dependencies]
    assert any(getattr(c, "__qualname__", "").startswith("require") or c.__module__.startswith("api.iam_deps")
               for c in dependants)


def test_threshold_warning(redis_client, monkeypatch, caplog):
    monkeypatch.setattr(monitoring.settings, "docling_cold_start_warn_per_hour", 6)
    redis_client.hset(cs.key_for(cs.hour_bucket(), "busy"), mapping={"cold:process_start": 7})
    redis_client.hset(cs.key_for(cs.hour_bucket(), "calm"), mapping={"cold:process_start": 6})
    with caplog.at_level(logging.WARNING):
        result = monitoring.check_docling_cold_starts()
    assert result["warned"] == ["busy"]
    assert any("worker=busy" in r.getMessage() for r in caplog.records)


def test_threshold_check_survives_redis_down(monkeypatch):
    monkeypatch.setattr(cs, "_redis_read", MagicMock(side_effect=ConnectionError("down")))
    assert monitoring.check_docling_cold_starts() == {"checked": 0, "warned": []}


def test_a_failed_build_does_not_count_as_seen(redis_client, monkeypatch):
    calls = {"n": 0}

    class Flaky:
        def __init__(self, **options):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(converter_module, "DoclingConverter", Flaky)
    with pytest.raises(RuntimeError):
        get_converter("fast")
    get_converter("fast")  # the retry is still the process's first build
    assert _reasons(redis_client)[0] == {"process_start": 1, "new_options": 0, "evicted": 0}


def test_telemetry_client_has_short_timeouts(monkeypatch):
    monkeypatch.undo()  # use the real factory, not the conftest fake
    cs._telemetry_client = None
    client = cs._redis()
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == kwargs["socket_connect_timeout"] == 0.5
    cs._telemetry_client = None
