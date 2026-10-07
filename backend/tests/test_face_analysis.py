"""Facial workflow contracts, recovery, isolation and v1 compatibility."""
import base64
import json
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.database import get_db
from shared.models import ImageAnalysisRun as Run, ImageAnalysisStep as Step, Job, Project
from shared.schemas import ImageFullOptions, FaceAnalyzeRequest, ConversionResult
from shared.face_analysis import FaceOptions, FaceRequestOptions, FullFaceOptions, select_faces, call_limits
from shared import image_analysis as lifecycle
from tests.test_image_full_analysis import memory, seed


@pytest.mark.parametrize('options', [
    {'max_faces': 0}, {'max_faces': 11}, {'max_faces': True}, {'max_faces': 1.5},
    {'min_detection_confidence': float('nan')}, {'min_expression_score': float('inf')},
    {'tracking_confidence': .5}, {'mode': 'detection', 'min_expression_score': .5},
    {'mode': 'detection', 'min_face_presence_confidence': .5}, {'deadline_seconds': 301},
])
def test_face_options_reject_invalid_or_ignored_parameters(options):
    with pytest.raises(ValueError):
        FaceRequestOptions(**options)


def test_profiles_have_separate_contracts_and_budgets():
    with pytest.raises(ValueError): FullFaceOptions(max_faces=6)
    with pytest.raises(ValueError): FullFaceOptions(mode='detection')
    with pytest.raises(ValueError): ImageFullOptions(faces={})
    assert ImageFullOptions().profile == 'image-full-v1'
    options = ImageFullOptions(profile='image-full-v2').model_dump()
    assert options['faces']['max_faces'] == 5
    assert call_limits({'full_options': options}) == {'florence': 32, 'face': 22, 'total': 54}
    assert call_limits({'mode': 'faces', 'face_options': FaceOptions(max_faces=10).effective()})['total'] == 42
    assert call_limits({'mode': 'faces', 'face_options': FaceOptions(mode='detection').effective()})['total'] == 2
    assert 'min_expression_score' not in FaceOptions(mode='detection').effective()


def test_face_selection_is_deterministic_clamped_and_limited():
    candidates = [{'bbox': [0, 0, 5, 5], 'detection_confidence': .7, 'keypoints': []},
                  {'bbox': [-1, -1, 10, 10], 'detection_confidence': .9, 'keypoints': []}]
    result = select_faces(candidates, FaceOptions(max_faces=1).effective(), 20, 20)
    assert result['faces'][0]['face_id'] == 'face-001'
    assert result['faces'][0]['bbox'] == [0, 0, 10, 10]
    assert result['faces'][0]['bbox_normalized'] == [0, 0, .5, .5]
    assert result['detected_count'] == 2 and result['omitted_count'] == 1
    assert result == select_faces(list(reversed(candidates)), FaceOptions(max_faces=1).effective(), 20, 20)


def facial_seed(memory, *, full=False, mode='expressions'):
    job_id = seed(memory)
    with memory[0]() as db:
        run = db.get(Run, job_id)
        options = dict(run.options)
        options['face_models'] = []
        if full:
            options['mode'] = 'full'
            options['full_options'] = ImageFullOptions(profile='image-full-v2').model_dump()
            run.profile = 'image-full-v2'
        else:
            options['mode'] = 'faces'
            options['face_options'] = FaceRequestOptions(mode=mode).effective()
            options.pop('full_options')
            run.profile = 'image-faces-v1'
        run.options = options
        db.commit()
    return job_id


class Pipeline:
    empty = False
    failed = None
    def __init__(self, *args): pass
    def close(self): pass
    def analyze(self, bitmap, item):
        if item['task'] == self.failed:
            from workers.vision.faces import FaceFailure
            raise FaceFailure('controlled_failure')
        if item['task'] == 'face_detection':
            return {'output': {'faces': [] if self.empty else [{
                'face_id': 'face-001', 'bbox': [1, 2, 20, 22], 'bbox_normalized': [1/32, 2/24, 20/32, 22/24],
                'detection_confidence': .9, 'crop': [0, 0, 25, 24], 'keypoints': []}],
                'detected_count': 0 if self.empty else 1, 'selected_count': 0 if self.empty else 1,
                'omitted_count': 0, 'selection_limited': False}}
        if item['task'] == 'face_movements':
            return {'output': {'landmarks': [], 'blendshapes': [{'name': 'mouthSmileLeft', 'score': .75}]}}
        return {'output': {'label': None, 'decision': 'inconclusive', 'scores': [{'label': 'Neutral', 'score': .4}], 'calibrated': False}}


@pytest.mark.parametrize('full', [False, True])
@pytest.mark.parametrize('empty, failed, expected', [(False, None, 'completed'), (True, None, 'completed'),
    (False, 'face_movements', 'partial'), (False, 'face_detection', None)])
def test_worker_persists_faces_and_full_with_explicit_coverage(memory, monkeypatch, full, empty, failed, expected):
    from workers.image_full_tasks import run_full_image_task
    from workers.vision import faces
    monkeypatch.setattr(faces, 'FacePipeline', Pipeline)
    monkeypatch.setattr(Pipeline, 'empty', empty)
    monkeypatch.setattr(Pipeline, 'failed', failed)
    job_id = facial_seed(memory, full=full)
    run_full_image_task.run(job_id=job_id)
    with memory[0]() as db:
        job = db.get(Job, job_id)
        assert job.minio_result_path
        result = json.loads(memory[1].objects[job.minio_result_path])
        image = result['image']
        assert image['analysis_status'] == (expected or ('partial' if full else 'failed'))
        assert image['coverage']['task_families_total'] == (18 if full else 3)
        assert db.get(Run, job_id).calls_by_provider.get('mediapipe')
        ConversionResult.model_validate(result)
    block = image['faces'] if full else image
    if failed != 'face_detection':
        assert len(block['faces']) == (0 if empty else 1)
        if not empty:
            assert block['faces'][0]['expression']['decision'] == 'inconclusive'
    if full:
        assert all('kind' in step for step in image['results'])
        assert any(s['kind'] == 'florence' for s in image['results'])


def test_detection_only_never_runs_expression_models(memory, monkeypatch):
    from workers.image_full_tasks import run_full_image_task
    from workers.vision import faces
    monkeypatch.setattr(faces, 'FacePipeline', Pipeline)
    job_id = facial_seed(memory, mode='detection')
    run_full_image_task.run(job_id=job_id)
    with memory[0]() as db:
        run = db.get(Run, job_id)
        assert run.calls_started == 1
        assert run.calls_by_provider == {'mediapipe': 1}
        result = json.loads(memory[1].objects[db.get(Job, job_id).minio_result_path])['image']
        assert result['coverage']['task_families_total'] == 1
        assert result['faces'][0]['expression']['reason_code'] == 'not_requested'


def test_face_selection_is_checkpointed_and_not_replanned_on_redelivery(memory):
    job_id = facial_seed(memory)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    detection = lifecycle.next_step(job_id, holder, fence)
    lifecycle.save_step(job_id, holder, fence, detection, Pipeline().analyze(None, detection), memory[1])
    assert lifecycle.resolve_faces(job_id, holder, fence, memory[1])
    assert not lifecycle.resolve_faces(job_id, holder, fence, memory[1])
    uncertain = lifecycle.next_step(job_id, holder, fence)
    with memory[0]() as db:
        db.get(Run, job_id).lease_until = datetime.utcnow()-timedelta(seconds=1); db.commit()
    new_holder = str(uuid4()); new_fence, *_ = lifecycle.claim(job_id, new_holder)
    retried = lifecycle.next_step(job_id, new_holder, new_fence)
    assert retried['step_id'] == uncertain['step_id'] and retried['input'] == uncertain['input']
    with memory[0]() as db:
        assert db.query(Step).filter_by(job_id=job_id, task='face_detection').count() == 1
        assert db.get(Run, job_id).calls_started == 3


def test_json_upload_parity_replay_and_unknown_fields(memory, monkeypatch):
    from api import face_routes, image_routes, image_full_routes
    from api.deps import get_current_active_user
    from workers import image_full_tasks
    factory, storage, user = memory
    monkeypatch.setattr(image_full_routes, 'get_minio_client', lambda: storage)
    monkeypatch.setattr(image_full_tasks, 'dispatch', lambda *args: None)
    monkeypatch.setattr(face_routes, 'require_faces', lambda mode: {'models': []})
    app = FastAPI(); app.include_router(face_routes.router); app.include_router(image_routes.router)
    def db_dependency():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_active_user] = lambda: user
    with factory() as db:
        project = Project(id=str(uuid4()), user_id=user.id, name='faces', name_key='faces'); db.add(project); db.commit()
    raw = next(iter(storage.objects.values()), None)
    if raw is None:
        temporary = seed(memory); raw = storage.objects[f'images/{temporary}/source']
    client = TestClient(app)
    body = {'image_base64': base64.b64encode(raw).decode(), 'filename': 'fixture.png', 'project_id': project.id}
    headers = {'Idempotency-Key': 'face-parity'}
    first = client.post('/images/faces', json=body, headers=headers)
    assert first.status_code == 202, first.text
    repeated = client.post('/images/faces/upload', data={'project_id': project.id}, files={'file': ('fixture.png', raw)}, headers=headers)
    assert repeated.status_code == 202, repeated.text
    assert first.json()['job_id'] == repeated.json()['job_id']
    assert client.post('/images/faces', json={**body, 'face_options': {'max_faces': 1}}, headers=headers).status_code == 409
    assert client.post('/images/faces', json=body).status_code == 422
    assert client.post('/images/faces/upload', data={'project_id': project.id, 'tracking': 'true'}, files={'file': ('fixture.png', raw)}, headers={'Idempotency-Key': 'other'}).status_code == 422
    assert client.post(f"/images/{first.json()['job_id']}/cancel").status_code == 202


def test_required_stages_are_checked_without_silent_fallback(monkeypatch):
    from api import face_routes
    monkeypatch.setattr(face_routes, 'face_capabilities', lambda: {'enabled': True, 'stages': {'face_detection': {'ready': True}}, 'models': []})
    assert face_routes.require_faces('detection')['enabled']
    with pytest.raises(Exception) as failed:
        face_routes.require_faces('expressions')
    assert failed.value.status_code == 503


def test_florence_load_failure_preserves_completed_facial_analysis(memory, monkeypatch):
    from workers.image_full_tasks import run_full_image_task
    from workers.vision import faces, factory
    monkeypatch.setattr(faces, 'FacePipeline', Pipeline)
    def unavailable():
        raise RuntimeError('Native provider unavailable')
    monkeypatch.setattr(factory, 'get_image_describer', unavailable)
    job_id = facial_seed(memory, full=True)
    run_full_image_task.run(job_id=job_id)
    with memory[0]() as db:
        payload = json.loads(memory[1].objects[db.get(Job, job_id).minio_result_path])
    assert payload['image']['analysis_status'] == 'partial'
    assert payload['image']['faces']['coverage']['task_families_completed'] == 3
    assert any(r['kind'] == 'florence' and r['status'] == 'failed' for r in payload['image']['results'])


def test_facial_budget_does_not_consume_the_florence_reserve(memory):
    job_id = facial_seed(memory, full=True)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    with memory[0]() as db:
        run = db.get(Run, job_id); run.calls_started = 22; run.calls_by_provider = {'mediapipe': 22}; db.commit()
    assert lifecycle.next_step(job_id, holder, fence) == 'limit'
    native = lifecycle.next_step(job_id, holder, fence)
    assert native['task'].startswith('<')


def test_facial_migration_is_additive_and_repeatable():
    from sqlalchemy import create_engine, text, inspect
    from shared.face_analysis_migration import migrate
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE image_analysis_runs (job_id VARCHAR(36) PRIMARY KEY)'))
        db.execute(text('CREATE TABLE image_analysis_steps (id INTEGER PRIMARY KEY)'))
        db.execute(text("INSERT INTO image_analysis_runs (job_id) VALUES ('existing')"))
        migrate(db); migrate(db)
        existing = db.execute(text('SELECT profile,calls_by_provider,faces_resolved FROM image_analysis_runs')).one()
        assert existing == ('image-full-v1', '{}', 0)
        assert {'step_kind', 'provider'} <= {c['name'] for c in inspect(db).get_columns('image_analysis_steps')}
    engine.dispose()
