"""A slow Celery health probe must leave the API event loop available."""
import asyncio
import threading
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from api import routes
from workers.celery_app import celery_app


def test_health_probe_does_not_block_other_requests(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def stats():
        entered.set()
        if not release.wait(3):
            raise RuntimeError('Probe was not released while serving another request')
        return {'worker': {}}

    monkeypatch.setattr(routes, 'get_redis_client', lambda: SimpleNamespace(ping=lambda: True))
    monkeypatch.setattr(routes, 'get_es_client', lambda: SimpleNamespace(health_check=lambda: True))
    monkeypatch.setattr(celery_app.control, 'inspect', lambda: SimpleNamespace(stats=stats))
    app = FastAPI()
    app.include_router(routes.router)

    @app.get('/responsive')
    async def responsive():
        return {'ok': True}

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            health = asyncio.create_task(client.get('/health'))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                response = await client.get('/responsive')
                assert response.json() == {'ok': True}
                assert not health.done(), 'The health probe blocked the API event loop'
            finally:
                release.set()
                result = await health
            assert result.status_code == 200
            assert result.json()['workers']['active'] == 1

    asyncio.run(exercise())
