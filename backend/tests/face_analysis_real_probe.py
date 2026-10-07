"""Real facial and Full-v2 inference in isolated SQLite/storage, no production jobs.

Set FACE_ANALYSIS_ENABLED=true and mount pinned artifacts at FACE_MODEL_CACHE_DIR.
Pass a licensed fixture image; use DEVICE=cuda and cached Florence weights for Full.
"""
import argparse
import hashlib
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base
from shared.models import Job, User, ImageAnalysisRun as Run
from shared.schemas import ImageFullOptions, ConversionResult
from shared.face_analysis import FaceRequestOptions
from shared.config import get_settings
from shared import image_analysis as lifecycle
from workers import image_full_tasks as tasks
from workers.vision.faces import capabilities


def run(image_path):
    with tempfile.TemporaryDirectory(prefix='face-real-') as directory:
        root = Path(directory)
        engine = create_engine('sqlite:///'+str(root/'db.sqlite'), connect_args={'check_same_thread': False})
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        lifecycle.SessionLocal = tasks.SessionLocal = factory
        settings = get_settings(); settings.temp_storage_path = str(root/'handoff')
        class Storage:
            bucket_results = 'private-test'
            def upload_file(self, bucket_name, object_name, file_data, **kwargs):
                path = root/'objects'/object_name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(file_data); return object_name
            def download_file(self, bucket, key): return (root/'objects'/key).read_bytes()
            def delete_file(self, bucket, key): (root/'objects'/key).unlink(missing_ok=True)
            def delete_folder(self, bucket, prefix): return True
        storage = Storage(); tasks.get_minio_client = lambda: storage
        from shared.datalake import service
        service.enqueue_export = lambda *args, **kwargs: None
        raw = Path(image_path).read_bytes()
        answers = []
        for full in (False, True):
            job_id, user_id = str(uuid4()), str(uuid4())
            source = f'images/{job_id}/source'; storage.upload_file('private-test', source, raw)
            config = {'mode': 'full' if full else 'faces', 'provider': settings.vision_provider,
                      'model': {'model_id': settings.vision_model_id, 'revision': settings.vision_model_revision, 'device': 'pending', 'dtype': 'pending'},
                      'face_models': capabilities()['models']}
            if full:
                config['full_options'] = ImageFullOptions(profile='image-full-v2', faces={'max_faces': 1},
                    generation={'max_new_tokens': 256, 'num_beams': 1}).model_dump()
            else:
                config['face_options'] = FaceRequestOptions(max_faces=1).effective()
            with factory() as db:
                db.add(User(id=user_id, username=job_id, email=f'{job_id}@example.invalid', hashed_password='unused', is_active=True)); db.flush()
                db.add(Job(id=job_id, user_id=user_id, source_type='image', filename='licensed-fixture.png', mime_type='image/png',
                           file_size_bytes=len(raw), file_checksum=hashlib.sha256(raw).hexdigest(), job_type='MAIN')); db.flush()
                db.add(Run(job_id=job_id, profile='image-full-v2' if full else 'image-faces-v1', source_path=source,
                           deadline_at=datetime.utcnow()+timedelta(seconds=900), dispatch_after=datetime.utcnow(), options=config)); db.commit()
            started = time.monotonic(); response = tasks.run_full_image_task.run(job_id)
            with factory() as db:
                job = db.get(Job, job_id); assert job.minio_result_path, response
                payload = json.loads(storage.download_file('private-test', job.minio_result_path))
            ConversionResult.model_validate(payload)
            image = payload['image']; facial = image['faces'] if full else image
            assert len(facial['faces']) == 1, facial['detection']
            face = facial['faces'][0]
            assert len(face['movements']['landmarks']) == 478
            assert len(face['movements']['blendshapes']) == 52
            assert len(face['expression']['scores']) == 8
            answers.append(facial)
            print(json.dumps({'profile': image['profile'], 'status': image['analysis_status'],
                              'families': image['coverage']['task_families_total'], 'completed': image['coverage']['task_families_completed'],
                              'calls': image['calls_started'], 'calls_by_provider': image['calls_by_provider'],
                              'seconds': round(time.monotonic()-started, 3), 'landmarks': 478, 'blendshapes': 52, 'classes': 8}), flush=True)
        assert answers[0]['faces'][0]['bbox'] == answers[1]['faces'][0]['bbox']
        for before, after in zip(answers[0]['faces'][0]['expression']['scores'], answers[1]['faces'][0]['expression']['scores']):
            assert before['label'] == after['label'] and abs(before['score']-after['score']) <= 1e-5
        print('Dedicated/Full facial equivalence: <=1e-5', flush=True)
        engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    run(parser.parse_args().image)
