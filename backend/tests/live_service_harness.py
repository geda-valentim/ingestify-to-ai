"""Isolated GPU benchmark API harness; NEVER import from production apps.

Requires LIVE_TEST_DIR, SQLite database URL inside that directory and a Redis
host explicitly set to the dedicated test container. Artifact stand-ins persist
all four formats and Markdown on disk and raise on I/O failure; auth and
location use the real API code. GPU decoding runs in the separate private
worker service, unchanged. No production service/database is accessed.
"""
import asyncio
import os
from pathlib import Path
from contextlib import suppress
import json
from fastapi import FastAPI
from shared.config import get_settings
from shared.database import Base, engine, SessionLocal
from shared.models import User
from shared.auth import create_access_token
from api import live_routes, routes
from shared.live import persistence

root = Path(os.environ['LIVE_TEST_DIR']).resolve()
settings = get_settings()
if not settings.database_url.startswith('sqlite:///') or str(root) not in settings.database_url:
    raise RuntimeError('Harness requires an isolated SQLite path inside LIVE_TEST_DIR')
if settings.redis_host not in {'live-test-redis', '127.0.0.1', os.environ.get('LIVE_TEST_REDIS_HOST', '')}:
    raise RuntimeError('Harness requires a dedicated Redis test endpoint')
root.mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(engine)
with SessionLocal() as db:
    if not db.get(User, 'benchmark-user'):
        db.add(User(id='benchmark-user', username='benchmark', email='benchmark@example.test', hashed_password='unused'))
        db.commit()
(root / 'token').write_text(create_access_token({'sub': 'benchmark-user'}))
(root / 'token').chmod(0o600)


class DiskObjects:
    bucket_audio = 'audio-test'
    def upload_file(self, *, bucket_name, object_name, file_data, content_type):
        target = root / 'objects' / object_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_data)
        return object_name
    def download_file(self, *, bucket_name, object_name):
        target = root / 'objects' / object_name
        return target.read_bytes() if target.is_file() else None
    def delete_file(self, bucket_name, object_name):
        (root / 'objects' / object_name).unlink(missing_ok=True)
        return True
    def delete_folder(self, bucket_name, prefix):
        import shutil
        shutil.rmtree(root / 'objects' / prefix, ignore_errors=True)
        return True


class DiskIndex:
    def store_job_result(self, **kwargs):
        target = root / 'index' / (kwargs['job_id'] + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'markdown_content': kwargs['markdown_content'], 'metadata': kwargs['metadata']}, ensure_ascii=False))
        return True
    def get_job_result(self, job_id):
        target = root / 'index' / (job_id + '.json')
        return json.loads(target.read_text()) if target.is_file() else None
    def delete_job_result(self, job_id):
        (root / 'index' / (job_id + '.json')).unlink(missing_ok=True)
        return True
    def delete_all_page_results(self, job_id):
        return True


objects, index = DiskObjects(), DiskIndex()
persistence.get_minio_client = lambda: objects
routes.get_minio_client = lambda: objects
routes.get_es_client = lambda: index
live_routes.get_es_client = lambda: index
app = FastAPI()
app.include_router(live_routes.router)
app.include_router(routes.router)


@app.on_event('startup')
async def startup():
    app.state.sweeper = asyncio.create_task(live_routes.sweeper_loop())


@app.on_event('shutdown')
async def shutdown():
    app.state.sweeper.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.sweeper
