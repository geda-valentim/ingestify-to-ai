"""Full image contracts: bounded planning, SQL fencing, durable recovery and API."""
import base64
import functools
import io
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.database import Base, get_db
from shared.models import User, Job, JobStatus, ImageAnalysisRun as Run, ImageAnalysisStep as Step
from shared.schemas import ImageFullOptions, ImageFullAnalyzeRequest, ImageFullAnalysisResult
from shared.image_full import initial_steps, resolve_steps, coverage
from shared import image_analysis as lifecycle


class Storage:
    bucket_results = 'private'
    def __init__(self):
        self.objects = {}
    def upload_file(self, bucket_name, object_name, file_data, **kwargs):
        self.objects[object_name] = file_data
        return object_name
    def download_file(self, bucket, key):
        return self.objects[key]
    def delete_file(self, bucket, key):
        self.objects.pop(key, None)
    def delete_folder(self, bucket, prefix):
        for key in list(self.objects):
            if key.startswith(prefix): del self.objects[key]


@pytest.fixture
def memory(monkeypatch, tmp_path):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    storage = Storage()
    with factory() as db:
        user = User(id=str(uuid4()), username='full-test', email='full@example.invalid', hashed_password='unused', is_active=True)
        db.add(user); db.commit()
    monkeypatch.setattr(lifecycle, 'SessionLocal', factory)
    from workers import image_full_tasks as tasks
    monkeypatch.setattr(tasks, 'SessionLocal', factory)
    monkeypatch.setattr(tasks, 'get_minio_client', lambda: storage)
    from shared.datalake import service
    monkeypatch.setattr(service, 'enqueue_export', lambda *args, **kwargs: None)
    settings = tasks.get_settings()
    monkeypatch.setattr(settings, 'temp_storage_path', str(tmp_path))
    yield factory, storage, user
    engine.dispose()


def seed(memory, **changes):
    factory, storage, user = memory
    from shared.config import get_settings
    settings = get_settings()
    job_id = str(uuid4())
    source = f'images/{job_id}/source'
    from PIL import Image
    data = io.BytesIO(); Image.new('RGB', (32, 24), 'white').save(data, 'PNG')
    storage.objects[source] = data.getvalue()
    options = {'provider': settings.vision_provider, 'model': {'model_id': settings.vision_model_id,
        'revision': settings.vision_model_revision, 'device': 'cpu', 'dtype': 'float32'},
        'full_options': ImageFullOptions().model_dump()}
    with factory() as db:
        db.add(Job(id=job_id, user_id=user.id, source_type='image', filename='fixture.png', status=JobStatus.PENDING, job_type='MAIN', file_checksum=__import__('hashlib').sha256(data.getvalue()).hexdigest()))
        db.flush()
        row = Run(job_id=job_id, options=options, source_path=source, deadline_at=datetime.utcnow()+timedelta(minutes=10), dispatch_after=datetime.utcnow())
        for key, value in changes.items(): setattr(row, key, value)
        db.add(row); db.commit()
    return job_id


def test_full_default_uses_all_fifteen_families_and_has_bounded_fanout():
    base = initial_steps()
    assert len(base) == 8
    results = [{**s, 'status': 'succeeded', 'text': 'A car on a street', 'regions': []} for s in base]
    od = next(r for r in results if r['task'] == '<OD>')
    od['regions'] = [{'label': f'object-{i}', 'bbox': [i*10, 0, i*10+5, 5]} for i in range(6)]
    planned, inputs = resolve_steps(results, {}, 100, 100)
    assert len(results+planned) == 31
    assert len({r['task'] for r in results+planned}) == 15
    assert len(inputs['queries']) == 3 and len(inputs['regions']) == 4
    assert inputs['omitted_candidates']


def test_explicit_queries_and_regions_replace_derived_inputs():
    planned, inputs = resolve_steps([], {'queries': ['a dog'], 'regions': [[.1,.2,.5,.6]]}, 100, 100)
    assert planned[0]['input']['text_input'] == 'a dog'
    assert inputs['regions'][0]['origin'] == 'user'
    assert len(planned) == 7


@pytest.mark.parametrize('options', [{'queries': []}, {'queries': [' ']}, {'queries': ['a']*4},
    {'regions': [[0,0,float('nan'),1]]}, {'regions': [[.8,0,.2,1]]}, {'deadline_seconds': 901}])
def test_invalid_full_inputs_rejected(options):
    with pytest.raises(ValueError): ImageFullOptions(**options)


def test_native_fields_are_rejected_in_full_request():
    with pytest.raises(ValueError):
        ImageFullAnalyzeRequest(mode='full', image_base64='unused', task='<OCR>')


def test_call_counter_includes_uncertain_recovery_and_never_exceeds_cap(memory):
    job_id = seed(memory, calls_started=31)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    first = lifecycle.next_step(job_id, holder, fence)
    assert isinstance(first, dict)
    assert lifecycle.next_step(job_id, holder, fence) == 'limit'
    with memory[0]() as db: assert db.get(Run, job_id).calls_started == 32


def test_late_holder_cannot_publish_over_new_fence(memory):
    job_id = seed(memory)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    item = lifecycle.next_step(job_id, holder, fence)
    with memory[0]() as db:
        run = db.get(Run, job_id); run.fence += 1; db.commit()
    with pytest.raises(lifecycle.LostLease):
        lifecycle.save_step(job_id, holder, fence, item, {'text': 'stale', 'output': 'stale'}, memory[1])
    with memory[0]() as db:
        assert not db.query(Step).filter(Step.result_path.isnot(None)).count()
        assert db.get(Job, job_id).minio_result_path is None


def test_expired_admission_does_not_start_inference(memory):
    job_id = seed(memory, deadline_at=datetime.utcnow()-timedelta(seconds=1))
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    with pytest.raises(lifecycle.LostLease, match='deadline'):
        lifecycle.next_step(job_id, holder, fence)


def test_full_worker_publishes_durable_composite_without_redis(memory, monkeypatch):
    job_id = seed(memory)
    from workers.image_full_tasks import run_full_image_task
    from shared.redis_client import get_redis_client
    import shared.redis_client
    monkeypatch.setattr(shared.redis_client, 'get_redis_client', lambda: (_ for _ in ()).throw(RuntimeError('cache down')))
    response = run_full_image_task.run(job_id)
    with memory[0]() as db:
        job = db.get(Job, job_id)
        assert job.status == JobStatus.COMPLETED, response
        payload = json.loads(memory[1].objects[job.minio_result_path])
        typed = ImageFullAnalysisResult.model_validate(payload['image'])
        assert typed.coverage['task_families_completed'] == 15
        assert {r.task for r in typed.results} == set(__import__('shared.vision_capabilities', fromlist=['VISION_TASKS']).VISION_TASKS)
        assert typed.image_base64
        assert db.get(Run, job_id).calls_started <= 32


def test_finished_empty_output_counts_as_available_not_failed(memory):
    job_id = seed(memory)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    item = lifecycle.next_step(job_id, holder, fence)
    lifecycle.save_step(job_id, holder, fence, item, {'text': '', 'output': ''}, memory[1])
    payload = lifecycle.finish(job_id, holder, fence, memory[1], reason='deadline')
    assert payload['image']['analysis_status'] == 'partial'


def test_cancel_preserves_checkpoint_and_returns_terminal_envelope(memory):
    job_id = seed(memory)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    item = lifecycle.next_step(job_id, holder, fence)
    lifecycle.save_step(job_id, holder, fence, item, {'text': 'valid', 'output': 'valid'}, memory[1])
    with memory[0]() as db:
        run = db.get(Run, job_id); run.cancel_requested = True; db.commit()
    payload = lifecycle.finish(job_id, holder, fence, memory[1], reason='cancelled')
    assert payload['image']['analysis_status'] == 'cancelled'
    assert payload['image']['results'][0]['text'] == 'valid'


def test_json_and_multipart_are_idempotent_and_single_is_preserved(memory, monkeypatch):
    factory, storage, user = memory
    from shared.auth import get_current_active_user
    from api import image_routes, image_full_routes
    from workers import image_full_tasks
    from shared.models import Project
    with factory() as db:
        project = Project(id=str(uuid4()), user_id=user.id, name='Images', name_key='images')
        db.add(project); db.commit()
    def db_dependency():
        with factory() as db: yield db
    app = FastAPI(); app.include_router(image_routes.router)
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_active_user] = lambda: user
    monkeypatch.setattr(image_full_routes, 'get_minio_client', lambda: storage)
    monkeypatch.setattr(image_full_tasks, 'dispatch', lambda *args: None)
    from PIL import Image
    data = io.BytesIO(); Image.new('RGB', (8,8)).save(data, 'PNG'); raw = data.getvalue()
    client = TestClient(app)
    body = {'mode': 'full', 'image_base64': base64.b64encode(raw).decode(), 'filename': 'image.png', 'project_id': project.id}
    headers = {'Idempotency-Key': 'same-source'}
    first = client.post('/images/analyze', json=body, headers=headers)
    assert first.status_code == 202, first.text
    repeated = client.post('/images/analyze/upload', data={'mode': 'full', 'project_id': project.id}, files={'file': ('image.png', raw, 'image/png')}, headers=headers)
    assert repeated.status_code == 202, repeated.text
    assert first.json()['job_id'] == repeated.json()['job_id']
    changed = client.post('/images/analyze', json={**body, 'full_options': {'queries': ['different']}}, headers=headers)
    assert changed.status_code == 409
    missing = client.post('/images/analyze', json=body)
    assert missing.status_code == 422
    incompatible = client.post('/images/analyze/upload', data={'mode': 'full', 'task': '<OCR>', 'project_id': project.id}, files={'file': ('image.png', raw)}, headers={'Idempotency-Key': 'other'})
    assert incompatible.status_code == 422
    cancelled = client.post(f"/images/{first.json()['job_id']}/cancel")
    assert cancelled.status_code == 202


@pytest.mark.parametrize('mode', ['off', 'enforce'])
def test_cancel_requires_the_run_row_to_carry_the_callers_own_user_id(memory, monkeypatch, mode):
    """Main's rule was `Job.user_id == me` on the run's own row; a NULL-owner row that
    the shared job rule gives the caller through its parent stays a 404 (spec 0014 CA3)."""
    factory, storage, user = memory
    from shared.auth import get_current_active_user
    from shared.config import get_settings
    from api import image_routes
    monkeypatch.setattr(get_settings(), 'iam_mode', mode)
    with factory() as db:
        for job_id, owner, parent in (('own-image', user.id, None), ('parent-main', user.id, None),
                                      ('parented-image', None, 'parent-main')):
            db.add(Job(id=job_id, user_id=owner, parent_job_id=parent, name=job_id, filename='image.png',
                       status=JobStatus.PROCESSING, job_type='MAIN', created_at=datetime(2026, 1, 1)))
        db.flush()
        for job_id in ('own-image', 'parented-image'):
            db.add(Run(job_id=job_id, options={}, source_path=f'images/{job_id}/source',
                       deadline_at=datetime(2030, 1, 1)))
        db.commit()
    def db_dependency():
        with factory() as db: yield db
    app = FastAPI(); app.include_router(image_routes.router)
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_active_user] = lambda: user
    client = TestClient(app)
    refused = client.post('/images/parented-image/cancel')
    assert refused.status_code == 404 and refused.json()['detail'] == image_routes.FULL_ANALYSIS_NOT_FOUND
    with factory() as db:
        assert not db.get(Run, 'parented-image').cancel_requested
    assert client.post('/images/own-image/cancel').status_code == 202


def test_ocr_failure_is_not_a_caption_or_detection_dependency():
    results = [{**s, 'status': 'succeeded', 'text': '', 'regions': []} for s in initial_steps()]
    next(r for r in results if r['task'] == '<OCR>')['status'] = 'failed'
    planned, _ = resolve_steps(results, {}, 32, 24)
    text_steps = [r for r in planned if r['task'] in ('<CAPTION_TO_PHRASE_GROUNDING>', '<OPEN_VOCABULARY_DETECTION>', '<REFERRING_EXPRESSION_SEGMENTATION>')]
    assert all(r['status'] == 'not_applicable' and r['reason_code'] == 'no_valid_text_input' for r in text_steps)


def all_successful(memory, job_id):
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    with memory[0]() as db:
        for row in db.query(Step).filter_by(job_id=job_id): row.status = 'succeeded'
        extra, inputs = resolve_steps([{**s, 'status': 'succeeded', 'text': ''} for s in initial_steps()], {}, 32, 24)
        lifecycle.add_steps(db, job_id, extra)
        for row in db.query(Step).filter_by(job_id=job_id):
            if row.status == 'pending': row.status = 'succeeded'
        run = db.get(Run, job_id); run.resolved = True; run.resolved_inputs = inputs
        db.commit()
    return holder, fence


@pytest.mark.parametrize('change, expected', [('deadline', 'partial'), ('cancelled', 'cancelled'), ('owner', 'partial'), ('fence', None), ('lease', None)])
def test_report_revalidates_authority_after_object_io(memory, monkeypatch, change, expected):
    job_id = seed(memory)
    holder, fence = all_successful(memory, job_id)
    storage = memory[1]
    original = storage.upload_file
    changed = False
    def upload(*args, **kwargs):
        nonlocal changed
        outcome = original(*args, **kwargs)
        if '/reports/' in kwargs['object_name'] and not changed:
            changed = True
            # This transaction must run while the object upload is outside locks.
            with memory[0]() as db:
                run = db.get(Run, job_id)
                if change == 'deadline': run.deadline_at = datetime.utcnow()-timedelta(seconds=1)
                elif change == 'cancelled': run.cancel_requested = True
                elif change == 'owner': db.get(User, memory[2].id).is_active = False
                elif change == 'fence': run.fence += 1
                elif change == 'lease': run.lease_until = datetime.utcnow()-timedelta(seconds=1)
                db.commit()
        return outcome
    monkeypatch.setattr(storage, 'upload_file', upload)
    payload = lifecycle.finish(job_id, holder, fence, storage)
    if expected:
        assert payload['image']['analysis_status'] == expected
        assert payload['image']['reason_code']
    else:
        assert payload is None
        with memory[0]() as db: assert db.get(Job, job_id).minio_result_path is None
        assert not any('/reports/' in key for key in storage.objects)


def test_cancel_before_resolution_has_reason_for_all_fifteen_families(memory):
    job_id = seed(memory)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    with memory[0]() as db:
        db.get(Run, job_id).cancel_requested = True; db.commit()
    payload = lifecycle.finish(job_id, holder, fence, memory[1], reason='cancelled')
    assert len(payload['image']['results']) == 15
    assert all(f['instances'] and f['reason_codes'] == ['cancelled'] for f in payload['image']['coverage']['families'])


def test_source_corruption_is_detected_before_any_inference(memory):
    job_id = seed(memory)
    with memory[0]() as db: path = db.get(Run, job_id).source_path
    memory[1].objects[path] = b'corrupted'
    from workers.image_full_tasks import run_full_image_task
    result = run_full_image_task.run(job_id)
    assert result['reason_code'] == 'source_checksum_mismatch'
    with memory[0]() as db:
        assert db.get(Run, job_id).calls_started == 0
        assert db.get(Job, job_id).status == JobStatus.FAILED


def test_partial_step_failure_keeps_independent_outputs(memory, monkeypatch):
    job_id = seed(memory)
    from workers.vision.factory import get_image_describer
    model = get_image_describer(); original = model.analyze
    def analyze(path, options):
        if options['task'] == '<OCR>': raise RuntimeError('native task failed')
        return original(path, options)
    monkeypatch.setattr(model, 'analyze', analyze)
    from workers.image_full_tasks import run_full_image_task
    run_full_image_task.run(job_id)
    with memory[0]() as db:
        job = db.get(Job, job_id)
        payload = json.loads(memory[1].objects[job.minio_result_path])
        assert job.status == JobStatus.PARTIAL
        assert payload['image']['coverage']['task_families_completed'] == 14
        assert any(r['task'] == '<OCR>' and r['status'] == 'failed' for r in payload['image']['results'])


def test_redelivery_resumes_checkpoint_and_uses_only_one_recovery_call(memory):
    job_id = seed(memory)
    first_holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, first_holder)
    first = lifecycle.next_step(job_id, first_holder, fence)
    lifecycle.save_step(job_id, first_holder, fence, first, {'text': 'durable', 'output': 'durable'}, memory[1])
    interrupted = lifecycle.next_step(job_id, first_holder, fence)
    with memory[0]() as db:
        db.get(Run, job_id).lease_until = datetime.utcnow()-timedelta(seconds=1); db.commit()
    second_holder = str(uuid4()); new_fence, *_ = lifecycle.claim(job_id, second_holder)
    retried = lifecycle.next_step(job_id, second_holder, new_fence)
    assert retried['step_id'] == interrupted['step_id'] and retried['attempts'] == 2
    assert retried['step_id'] != first['step_id']
    with memory[0]() as db: assert db.get(Run, job_id).calls_started == 3


@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_bad_checkpoint_does_not_block_other_results(memory, damage):
    job_id = seed(memory)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    first = lifecycle.next_step(job_id, holder, fence)
    lifecycle.save_step(job_id, holder, fence, first, {'text': 'unavailable', 'output': 'unavailable'}, memory[1])
    second = lifecycle.next_step(job_id, holder, fence)
    lifecycle.save_step(job_id, holder, fence, second, {'text': 'preserved', 'output': 'preserved'}, memory[1])
    with memory[0]() as db: path = db.query(Step).filter_by(job_id=job_id, step_id=first['step_id']).one().result_path
    if damage == 'missing': del memory[1].objects[path]
    else: memory[1].objects[path] = b'corrupted'
    payload = lifecycle.finish(job_id, holder, fence, memory[1], reason='deadline')
    assert payload['image']['analysis_status'] == 'partial'
    assert payload['image']['results'][0]['status'] == 'failed'
    assert payload['image']['results'][1]['text'] == 'preserved'


def usage_seed(memory, job_id, status='reserved'):
    from shared.models import Engine, EngineUsage
    factory = memory[0]
    with factory() as db:
        engine = Engine(id=str(uuid4()), slug='full-local', display_name='Full test', adapter_type='local')
        db.add(engine); db.flush()
        usage = EngineUsage(engine_id=engine.id, feature='vision', subject_type='vision_request',
            subject_id=job_id, job_id=job_id, user_id=memory[2].id, period_start=datetime.utcnow().date(),
            status=status, holder='previous' if status == 'running' else None,
            heartbeat_at=datetime.utcnow()-timedelta(minutes=5), estimated_usd=0, reserved_usd=0)
        db.add(usage); db.flush()
        db.get(Run, job_id).usage_id = usage.id; db.commit()
        return usage.id


def test_lost_accounting_claim_waits_for_reconciliation_instead_of_terminating(memory, monkeypatch):
    job_id = seed(memory)
    usage_id = usage_seed(memory, job_id, 'running')
    from shared.engines import ledger
    monkeypatch.setattr(ledger, 'claim', functools.partial(ledger.claim, session_factory=memory[0]))
    from workers.image_full_tasks import run_full_image_task
    result = run_full_image_task.run(job_id)
    assert result['reason_code'] == 'accounting_claim_lost'
    with memory[0]() as db:
        run = db.get(Run, job_id)
        assert run.status == 'processing' and not run.holder and run.calls_started == 0
        assert db.get(Job, job_id).minio_result_path is None


@pytest.mark.parametrize('interrupt', [False, True])
def test_accounting_settlement_requires_durable_success(memory, monkeypatch, interrupt):
    job_id = seed(memory)
    usage_id = usage_seed(memory, job_id)
    from shared.engines import ledger
    for name in ('claim', 'heartbeat', 'settle_succeeded', 'settle_failed'):
        monkeypatch.setattr(ledger, name, functools.partial(getattr(ledger, name), session_factory=memory[0]))
    if interrupt:
        from workers.vision.factory import get_image_describer
        model = get_image_describer()
        monkeypatch.setattr(model, 'analyze', lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    from workers.image_full_tasks import run_full_image_task
    run_full_image_task.run(job_id)
    from shared.models import EngineUsage
    with memory[0]() as db:
        usage = db.get(EngineUsage, usage_id)
        assert usage.status == 'settled'
        assert usage.outcome == ('failed' if interrupt else 'succeeded')
        assert usage.measured_seconds is not None
        assert db.get(Job, job_id).minio_result_path


def test_crash_after_durable_report_reconciles_success_with_unknown_duration(memory):
    job_id = seed(memory)
    usage_id = usage_seed(memory, job_id)
    holder = str(uuid4()); fence, *_ = lifecycle.claim(job_id, holder)
    from shared.engines import ledger
    assert ledger.claim(usage_id, holder, session_factory=memory[0])[0] == ledger.CLAIMED
    with memory[0]() as db:
        for row in db.query(Step).filter_by(job_id=job_id): row.status = 'succeeded'
        extra, inputs = resolve_steps([{**s, 'status': 'succeeded', 'text': ''} for s in initial_steps()], {}, 32, 24)
        lifecycle.add_steps(db, job_id, extra)
        db.flush()
        for row in db.query(Step).filter_by(job_id=job_id):
            if row.status == 'pending': row.status = 'succeeded'
        db.commit()
    assert lifecycle.finish(job_id, holder, fence, memory[1])['image']['analysis_status'] == 'completed'
    from shared.models import EngineUsage
    with memory[0]() as db:
        db.get(EngineUsage, usage_id).heartbeat_at = datetime.utcnow()-timedelta(minutes=5); db.commit()
    outcome, _ = ledger.mark_lost(usage_id, stale_before=datetime.utcnow()-timedelta(seconds=90), session_factory=memory[0])
    assert outcome == 'succeeded'
    with memory[0]() as db:
        usage = db.get(EngineUsage, usage_id)
        assert usage.output_persisted_at and usage.measured_seconds is None
        assert usage.units['measurement'] == 'unavailable'


def test_migration_is_repeatable_and_preserves_existing_jobs(memory):
    from shared.image_analysis_migration import migrate
    engine = memory[0].kw['bind']
    job_id = seed(memory)
    with engine.begin() as connection:
        migrate(connection); migrate(connection)
    with memory[0]() as db: assert db.get(Job, job_id).status == JobStatus.PENDING


def test_owned_full_status_and_results_are_available_with_redis_down(memory, monkeypatch):
    factory, storage, user = memory
    job_id = seed(memory)
    from shared.job_configuration import save_configuration
    with factory() as db:
        save_configuration(db, db.get(Job, job_id), operation='image', options={'mode':'full'}, provider='stub', model='stub')
        db.commit()
    from workers.image_full_tasks import run_full_image_task
    run_full_image_task.run(job_id)
    from api import routes
    from shared.auth import get_current_active_user
    import api.deps
    class Unavailable:
        def __getattr__(self, key): return lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('cache unavailable'))
    monkeypatch.setattr(routes, 'get_redis_client', lambda: Unavailable())
    monkeypatch.setattr(routes, 'get_minio_client', lambda: storage)
    def dependency():
        with factory() as db: yield db
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[get_db] = dependency
    app.dependency_overrides[get_current_active_user] = lambda: user
    client = TestClient(app)
    status = client.get(f'/jobs/{job_id}')
    assert status.status_code == 200, status.text
    assert status.json()['image_analysis']['steps_completed'] == status.json()['image_analysis']['steps_total']
    result = client.get(f'/jobs/{job_id}/result')
    assert result.status_code == 200, result.text
    assert result.json()['result']['image']['operation'] == 'full_analysis'
    raw = client.get(f'/jobs/{job_id}/result?format=json')
    assert raw.status_code == 200 and raw.json()['image']['coverage']['task_families_total'] == 15
    # Same resource must remain private even when the cache cannot authorize it.
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id=str(uuid4()), is_active=True)
    denied = client.get(f'/jobs/{job_id}/result')
    assert denied.status_code == 404


def test_deleted_idempotency_tombstone_waits_for_confirmed_purge(memory):
    from shared.models import ImageAnalysisSubmission as Submission
    from api.image_full_routes import replay
    from fastapi import HTTPException
    job_id = seed(memory)
    with memory[0]() as db:
        db.add(Submission(user_id=memory[2].id, key_hash='key', request_hash='request', job_id=job_id,
            deleted_at=datetime.utcnow()-timedelta(days=2), purge_after=datetime.utcnow()-timedelta(minutes=1)))
        db.delete(db.get(Job, job_id)); db.commit()
        with pytest.raises(HTTPException) as exc: replay(db, memory[2].id, 'key', 'request')
        assert exc.value.status_code == 410 and db.query(Submission).count() == 1
    from workers.image_full_tasks import reconcile
    reconcile.run()
    with memory[0]() as db:
        row = db.query(Submission).one()
        assert row.purged_at
        assert replay(db, memory[2].id, 'key', 'request') is None
        assert not db.query(Submission).count()
    assert not any(job_id in key for key in memory[1].objects)


def test_derived_inputs_keep_candidate_audit_and_text_boundaries():
    from shared.image_full import clip_text
    text = ('word '*500).strip()
    assert len(clip_text(text)) <= 2000 and clip_text(text).endswith('word')
    results = [{**s,'status':'succeeded','text':text,'regions':[]} for s in initial_steps()]
    od = next(r for r in results if r['task']=='<OD>')
    od['regions'] = [{'label':'box','bbox':[0,0,20,20]}, {'label':'box','bbox':[0,0,20,20]}]
    planned, inputs = resolve_steps(results,{},100,100)
    assert len(inputs['considered_candidates']) == 4  # query, whole image, both OD candidates
    assert any(c.get('reason_code')=='duplicate_region' for c in inputs['omitted_candidates'])
    assert planned[0]['input']['input_truncated'] and len(planned[0]['input']['text_input'])<=2000
    explicit, _ = resolve_steps(results,{'queries':['user query']},100,100)
    assert explicit[0]['input']['source_step_id'] is None
