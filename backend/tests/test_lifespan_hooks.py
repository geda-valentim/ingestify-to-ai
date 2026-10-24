"""Startup/shutdown hooks run through `lifespan` (Starlette 1.x has no on_event) in the right order."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _quiet_task(events, name):
    async def run():
        events.append(f"{name}:start")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            events.append(f"{name}:cancelled")
            raise
    return run


@pytest.fixture
def api_boot(monkeypatch):
    from api import live_routes, main
    from shared import auth, database, elasticsearch_client, minio_client, redis_client
    from shared.access import seed

    events = []
    monkeypatch.setattr(database, "SessionLocal", MagicMock(side_effect=RuntimeError("no db in this test")))
    monkeypatch.setattr(auth, "validate_jwt_secret", lambda secret: events.append("jwt"))
    monkeypatch.setattr(main, "init_database_on_boot", lambda: events.append("init_db"))
    monkeypatch.setattr(seed, "seed_on_boot", lambda: events.append("seed"))
    for module, getter in ((elasticsearch_client, "get_es_client"), (redis_client, "get_redis_client"),
                           (minio_client, "get_minio_client")):
        monkeypatch.setattr(module, getter, lambda: MagicMock())
    monkeypatch.setattr(main.settings, "engines_watchdog_enabled", True)
    monkeypatch.setattr(main.settings, "live_transcription_enabled", True)
    monkeypatch.setattr(main, "_engines_watchdog", _quiet_task(events, "watchdog"))
    monkeypatch.setattr(live_routes, "sweeper_loop", _quiet_task(events, "sweeper"))
    return main, events


def _recorded(module, name, events):
    original = getattr(module, name)

    async def wrapper():
        events.append(f"{name}:begin")
        await original()
        events.append(f"{name}:end")

    return wrapper


def test_api_startup_runs_in_order_and_shutdown_in_reverse(api_boot, monkeypatch):
    main, events = api_boot
    for name in ("startup_event", "start_live_sweeper", "stop_live_sweeper", "shutdown_event"):
        monkeypatch.setattr(main, name, _recorded(main, name, events))

    with TestClient(main.app):
        events.append("serving")
        assert main.app.state.engines_watchdog is not None
        assert main.app.state.live_sweeper is not None

    assert [e for e in events if not e.startswith(("watchdog:", "sweeper:"))] == [
        "startup_event:begin", "jwt", "init_db", "seed", "startup_event:end",
        "start_live_sweeper:begin", "start_live_sweeper:end",
        "serving",
        "stop_live_sweeper:begin", "stop_live_sweeper:end",
        "shutdown_event:begin", "shutdown_event:end",
    ]
    assert main.app.state.live_sweeper.cancelled()
    assert main.app.state.engines_watchdog.cancelling() or main.app.state.engines_watchdog.cancelled()


def test_api_boot_aborts_when_the_jwt_secret_is_invalid(api_boot, monkeypatch):
    from shared import auth
    main, events = api_boot

    def refuse(secret):
        raise RuntimeError("insecure JWT secret")

    monkeypatch.setattr(auth, "validate_jwt_secret", refuse)

    with pytest.raises(RuntimeError, match="insecure JWT secret"):
        with TestClient(main.app):
            pytest.fail("the app must not serve with an insecure JWT secret")
    assert "init_db" not in events and "seed" not in events


def test_live_worker_startup_and_shutdown_run_through_lifespan(monkeypatch):
    from workers.live import server

    events = []
    redis = MagicMock()
    store = SimpleNamespace(redis=redis, worker_key="live:worker")
    monkeypatch.setattr(server, "load_resident", lambda: events.append("load_resident"))
    monkeypatch.setattr(server, "heartbeat", _quiet_task(events, "heartbeat"))
    monkeypatch.setattr(server, "warm_diarizers", _quiet_task(events, "diarizers"))
    monkeypatch.setattr(server, "get_store", lambda: store)
    # the real shutdown stops the executor and clears the globals: give it throwaway ones
    monkeypatch.setattr(server, "executor", ThreadPoolExecutor(1))
    monkeypatch.setattr(server, "heartbeat_task", None)
    monkeypatch.setattr(server, "diarizer_task", None)

    with TestClient(server.app):
        assert events[0] == "load_resident"
        assert server.heartbeat_task is not None and server.diarizer_task is not None
        events.append("serving")

    assert events.index("serving") > events.index("load_resident")
    assert server.heartbeat_task.done() and server.diarizer_task.done()
    redis.delete.assert_called_once_with("live:worker")
