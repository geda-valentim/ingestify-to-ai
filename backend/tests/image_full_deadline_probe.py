"""Integration gate: real prefork hard timeout after queue wait, isolated SQL/queue.

Run manually with backend deps and Redis: python backend/tests/image_full_deadline_probe.py.
Uses no production SQL, MinIO, engine route, GPU or capability heartbeat.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from uuid import uuid4

WORKER = '--worker' in sys.argv
ROOT = Path(os.environ.get('IMAGE_FULL_PROBE_ROOT') or tempfile.mkdtemp(prefix='image-full-deadline-'))
QUEUE = os.environ.get('IMAGE_FULL_PROBE_QUEUE') or 'image-full-probe-' + uuid4().hex
os.environ.update(DATABASE_URL='sqlite:///' + str(ROOT / 'db.sqlite'), VISION_PROVIDER='stub',
    ENGINE_CONTROL_ENABLED='false', IMAGE_FULL_PROBE_ROOT=str(ROOT), IMAGE_FULL_PROBE_QUEUE=QUEUE,
    VISION_PRELOAD_MODEL='false', TEMP_STORAGE_PATH=str(ROOT / 'handoff'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.database import Base, engine, SessionLocal
from shared.models import User, Job, JobStatus, ImageAnalysisRun as Run
from shared.schemas import ImageFullOptions
from shared.config import get_settings
from workers.celery_app import celery_app
from workers import image_full_tasks as tasks


class Storage:
    bucket_results = 'probe'
    def upload_file(self, bucket_name, object_name, file_data, **kwargs):
        path = ROOT / 'objects' / object_name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(file_data)
        return object_name
    def download_file(self, bucket, key): return (ROOT / 'objects' / key).read_bytes()
    def delete_file(self, bucket, key): (ROOT / 'objects' / key).unlink(missing_ok=True)


storage = Storage()
tasks.get_minio_client = lambda: storage
from shared.datalake import service
service.enqueue_export = lambda *args, **kwargs: None
# Do not write production status/cache keys from the diagnostic watchdog.
import shared.redis_client
shared.redis_client.get_redis_client = lambda: (_ for _ in ()).throw(RuntimeError('probe cache disabled'))


@celery_app.task(name='image_full_probe.block_queue')
def block_queue(): time.sleep(2.5)


if WORKER:
    from workers.vision.stub_describer import StubDescriber
    class HungModel(StubDescriber):
        def analyze(self, path, options):
            # Model/native code that does not return even after the soft signal.
            while True:
                try: time.sleep(60)
                except BaseException: continue
    from workers.vision import factory
    factory.get_image_describer = lambda: HungModel()
    celery_app.worker_main(['worker', '--pool=prefork', '--concurrency=1', '-Q', QUEUE,
        '--without-gossip', '--without-mingle', '--without-heartbeat', '--loglevel=INFO', '-n', QUEUE+'@%h'])
    sys.exit()

Base.metadata.create_all(engine)
log = ROOT / 'worker.log'
with log.open('w') as stream:
    process = subprocess.Popen([sys.executable, __file__, '--worker'], env=os.environ.copy(), stdout=stream, stderr=stream)
try:
    start = time.monotonic()
    while ' ready.' not in log.read_text():
        assert process.poll() is None, 'Probe worker failed to boot'
        assert time.monotonic()-start < 25, 'Probe worker startup timeout'
        time.sleep(.1)
    from PIL import Image
    data = io.BytesIO(); Image.new('RGB', (16,16)).save(data, 'PNG'); raw = data.getvalue()
    job_id = str(uuid4()); user_id = str(uuid4()); source = f'images/{job_id}/source'
    storage.upload_file('probe', source, raw)
    settings = get_settings()
    admitted = datetime.utcnow()
    with SessionLocal() as db:
        db.add(User(id=user_id, username='deadline-probe', email='probe@example.invalid', hashed_password='unused', is_active=True)); db.flush()
        db.add(Job(id=job_id, user_id=user_id, source_type='image', filename='probe.png', status=JobStatus.PENDING,
            job_type='MAIN', file_checksum=hashlib.sha256(raw).hexdigest())); db.flush()
        db.add(Run(job_id=job_id, source_path=source, options={'provider':'stub',
            'model': {'model_id':settings.vision_model_id, 'revision':settings.vision_model_revision,'device':'cpu','dtype':'float32'},
            'full_options':ImageFullOptions(deadline_seconds=6).model_dump()}, deadline_at=admitted+timedelta(seconds=6), dispatch_after=admitted)); db.commit()
    blocker = block_queue.apply_async(queue=QUEUE)
    batch = tasks.run_full_image_task.apply_async(kwargs={'job_id':job_id}, queue=QUEUE)
    while 'Hard time limit (' not in log.read_text():
        assert (datetime.utcnow()-admitted).total_seconds() < 9, 'Hard timer did not include queue wait'
        time.sleep(.1)
    elapsed = (datetime.utcnow()-admitted).total_seconds()
    with SessionLocal() as db:
        run = db.get(Run, job_id)
        assert run.calls_started == 1, f'Unexpected calls: {run.calls_started}'
        assert (db.get(Job, job_id).started_at-admitted).total_seconds() >= 2.3, 'No queue wait measured'
    # Reconcile publishes only diagnostics; it does not rerun a killed native call.
    tasks.reconcile.run()
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.status == JobStatus.FAILED and job.minio_result_path
        payload = json.loads(storage.download_file('probe', job.minio_result_path))
        assert payload['image']['reason_code'] == 'deadline'
        assert len(payload['image']['results']) == 15
    print(f'PASS queue wait >=2.3s + hung inference: hard kill at {elapsed:.1f}s of 6s total deadline; watchdog retained 15-family diagnostics', flush=True)
    blocker.forget(); batch.forget()
finally:
    process.terminate()
    try: process.wait(timeout=10)
    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    # Delete only this unique test queue, never purge the application's queues.
    with celery_app.connection_for_write() as connection:
        connection.channel().queue_delete(QUEUE)
