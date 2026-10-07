"""Qualify full orchestration with cached Florence weights and isolated storage/SQL.

Run inside the vision worker image with GPU/cache mounts. No production records.
"""
import hashlib
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from uuid import uuid4
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PIL import Image, ImageDraw
from shared.database import Base
from shared.models import Job, JobStatus, User, ImageAnalysisRun as Run
from shared.schemas import ImageFullOptions, ImageFullAnalysisResult
from shared.config import get_settings
from shared import image_analysis as lifecycle
from workers import image_full_tasks as tasks

root = Path(tempfile.mkdtemp(prefix='image-full-real-'))
engine = create_engine('sqlite:///'+str(root/'db.sqlite'), connect_args={'check_same_thread':False})
Base.metadata.create_all(engine)
factory = sessionmaker(bind=engine)
lifecycle.SessionLocal = tasks.SessionLocal = factory
settings = get_settings(); settings.temp_storage_path = str(root/'handoff')


class Storage:
    bucket_results = 'private-test'
    def upload_file(self, bucket_name, object_name, file_data, **kwargs):
        path = root/'objects'/object_name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(file_data)
        return object_name
    def download_file(self, bucket, key): return (root/'objects'/key).read_bytes()
    def delete_file(self, bucket, key): (root/'objects'/key).unlink(missing_ok=True)
    def delete_folder(self, bucket, prefix): return True


storage = Storage(); tasks.get_minio_client = lambda:storage
from shared.datalake import service
service.enqueue_export = lambda *args, **kwargs:None
import shared.redis_client
shared.redis_client.get_redis_client = lambda: (_ for _ in ()).throw(RuntimeError('isolated probe cache'))

for scenario in sys.argv[1:] or ('automatic', 'explicit', 'blank'):
    job_id, user_id = str(uuid4()), str(uuid4())
    bitmap = Image.new('RGB',(320,240),'white'); draw = ImageDraw.Draw(bitmap)
    if scenario != 'blank':
        draw.text((30,30),'INVOICE 42\nTOTAL $12.00',fill='black',spacing=10)
        draw.rectangle((45,100,135,200),fill='red'); draw.ellipse((180,100,260,180),fill='blue')
    data=io.BytesIO(); exif=Image.Exif(); exif[274]=6; bitmap.save(data,'JPEG',exif=exif)
    raw=data.getvalue(); source=f'images/{job_id}/source'; storage.upload_file('private-test',source,raw)
    advanced = {'queries':['a receipt','a red rectangle','a blue circle'],
        'regions':[[0,0,1,1],[.1,.1,.6,.5],[.1,.4,.5,.95],[.5,.4,.9,.9]]} if scenario=='explicit' else {}
    options = ImageFullOptions(**advanced,generation={'max_new_tokens':64,'num_beams':1}).model_dump()
    with factory() as db:
        db.add(User(id=user_id,username=scenario,email=f'{scenario}@example.invalid',hashed_password='unused',is_active=True)); db.flush()
        db.add(Job(id=job_id,user_id=user_id,source_type='image',filename='receipt.jpg',mime_type='image/jpeg',
            file_size_bytes=len(raw),file_checksum=hashlib.sha256(raw).hexdigest(),job_type='MAIN',status=JobStatus.PENDING)); db.flush()
        db.add(Run(job_id=job_id,source_path=source,deadline_at=datetime.utcnow()+timedelta(seconds=180),dispatch_after=datetime.utcnow(),
            options={'provider':settings.vision_provider,'model':{'model_id':settings.vision_model_id,'revision':settings.vision_model_revision,
            'device':'pending','dtype':'pending'},'full_options':options})); db.commit()
    response=tasks.run_full_image_task.run(job_id)
    with factory() as db:
        job=db.get(Job,job_id); assert job.minio_result_path, response
        payload=json.loads(storage.download_file('private-test',job.minio_result_path))
        result=ImageFullAnalysisResult.model_validate(payload['image'])
        assert result.width==320 and result.height==240
        preview=Image.open(io.BytesIO(__import__('base64').b64decode(result.image_base64)))
        assert preview.format=='PNG' and preview.size==(320,240) and not preview.getexif().get(274)
        assert len({s.task for s in result.results})==15 and result.calls_started<=32
        if scenario=='explicit': assert result.calls_started==31
        assert any(s.status=='succeeded' and s.text for s in result.results)
        assert result.source_sha256==hashlib.sha256(raw).hexdigest()
        print(json.dumps({'scenario':scenario,'model':result.model.model_id,'device':result.model.device,
            'status':result.analysis_status,'families':result.coverage['task_families_total'],
            'completed_families':result.coverage['task_families_completed'],'calls':result.calls_started,
            'truncated':sum(s.truncated for s in result.results),'failed':sum(s.status=='failed' for s in result.results),
            'canonical_preview':'PNG 320x240, EXIF removed'},ensure_ascii=False),flush=True)
engine.dispose()
