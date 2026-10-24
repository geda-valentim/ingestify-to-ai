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


@pytest.mark.parametrize("dep", [auth.get_current_user, auth.get_current_active_user, auth.get_optional_user])
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
