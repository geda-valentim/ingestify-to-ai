"""Guard: blocking sync work must not run on the API event loop.

Live transcription WebSockets share the loop with every `async def` endpoint and
dependency; a stalled loop drops them with LIVE_BACKPRESSURE.
"""
import asyncio
import inspect
import time

import pytest

from api.main import app
from shared import auth

# Hot-path endpoints that do sync Redis/MySQL work: they must be plain `def`.
SYNC_ENDPOINTS = {
    ("GET", "/health"),
    ("GET", "/jobs/{job_id}"),
    ("GET", "/jobs/{job_id}/pages"),
    ("GET", "/jobs/{job_id}/transcript/partial"),
}


def _endpoints():
    for route in app.routes:
        for method in getattr(route, "methods", None) or ():
            yield method, route.path, route.endpoint


def test_hot_path_endpoints_are_not_coroutines():
    found = set()
    for method, path, endpoint in _endpoints():
        if (method, path) in SYNC_ENDPOINTS:
            found.add((method, path))
            assert not inspect.iscoroutinefunction(endpoint), f"{method} {path} blocks the loop"
    assert found == SYNC_ENDPOINTS


@pytest.mark.parametrize("dep", [auth.get_current_user, auth.get_optional_user])
def test_auth_dependencies_are_not_coroutines(dep):
    assert not inspect.iscoroutinefunction(dep)


def test_loop_stays_responsive_during_blocking_dependency():
    """A slow sync dependency runs in the threadpool, not on the loop."""
    from fastapi import Depends, FastAPI
    from httpx import ASGITransport, AsyncClient

    def slow_dep():
        time.sleep(0.5)
        return 1

    mini = FastAPI()

    @mini.get("/slow")
    def slow(_=Depends(slow_dep)):
        return {}

    @mini.get("/fast")
    async def fast():
        return {}

    async def run():
        async with AsyncClient(transport=ASGITransport(app=mini), base_url="http://t") as c:
            slow_task = asyncio.create_task(c.get("/slow"))
            await asyncio.sleep(0.05)
            t0 = time.monotonic()
            await c.get("/fast")
            elapsed = time.monotonic() - t0
            await slow_task
            return elapsed

    assert asyncio.run(run()) < 0.25


def _health_env(monkeypatch, routes, inspect_fn):
    from types import SimpleNamespace

    monkeypatch.setattr(routes, "get_redis_client", lambda: SimpleNamespace(ping=lambda: True))
    monkeypatch.setattr(routes, "get_es_client", lambda: SimpleNamespace(health_check=lambda: True))
    from workers.celery_app import celery_app
    monkeypatch.setattr(celery_app.control, "inspect", inspect_fn)
    monkeypatch.setitem(routes._health_cache, "payload", None)
    monkeypatch.setitem(routes._health_cache, "at", 0.0)


def test_health_is_cached(monkeypatch):
    from types import SimpleNamespace

    from api import routes

    calls = []

    def fake_inspect(**kw):
        calls.append(kw)
        return SimpleNamespace(stats=lambda: {"w1": {}})

    _health_env(monkeypatch, routes, fake_inspect)
    routes.health_check()
    routes.health_check()
    assert len(calls) == 1


def test_health_concurrent_call_does_not_wait(monkeypatch):
    import threading
    from types import SimpleNamespace

    from fastapi import HTTPException

    from api import routes

    release = threading.Event()
    started = threading.Event()

    def slow_inspect(**kw):
        started.set()
        release.wait(5)
        return SimpleNamespace(stats=lambda: {"w1": {}})

    _health_env(monkeypatch, routes, slow_inspect)
    t = threading.Thread(target=routes.health_check)
    t.start()
    assert started.wait(2)
    t0 = time.monotonic()
    with pytest.raises(HTTPException) as exc:
        routes.health_check()  # no cached result yet: 503, without waiting
    assert time.monotonic() - t0 < 0.5
    assert exc.value.status_code == 503
    release.set()
    t.join()


def test_health_unhealthy_is_503_not_500(monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import routes

    _health_env(monkeypatch, routes, lambda **kw: SimpleNamespace(stats=lambda: {}))
    mini = FastAPI()
    mini.include_router(routes.router)
    r = TestClient(mini).get("/health")
    assert r.status_code == 503
    assert r.json()["detail"]["status"] == "unhealthy"
