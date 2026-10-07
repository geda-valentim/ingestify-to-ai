"""Exercise native exports through page workers, cache loss and the real merge task."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from shared.document_capabilities import document_options
from shared.job_configuration import save_configuration
from shared.models import Job, JobStatus, Page
from workers import tasks, document_outputs
from tests.test_document_capabilities import make_document
from tests.test_upload_projects import db, env  # noqa: F401
from tests.test_tasks_page_conversion import session_local, run_task, RetryCalled  # noqa: F401


@pytest.fixture
def pipeline(monkeypatch, fake_redis, session_local, tmp_path):
    objects = {}
    storage = MagicMock()
    storage.bucket_results = 'results'
    def upload_file(*, bucket_name, object_name, file_data=None, file_path=None, **kwargs):
        objects[bucket_name, object_name] = file_data if file_data is not None else Path(file_path).read_bytes()
        return True
    storage.upload_file.side_effect = upload_file
    storage.download_file.side_effect = lambda bucket, name: objects[bucket, name]
    for module in [tasks, document_outputs]:
        monkeypatch.setattr(module, 'get_minio_client', lambda: storage)
    monkeypatch.setattr(tasks, 'SessionLocal', session_local)
    monkeypatch.setattr(tasks, 'get_redis_client', lambda: fake_redis)
    search = MagicMock()
    search.store_page_result.return_value = True
    search.store_job_result.return_value = True
    monkeypatch.setattr(tasks, 'get_es_client', lambda: search)
    monkeypatch.setattr(tasks.settings, 'temp_storage_path', str(tmp_path))
    monkeypatch.setattr(tasks, '_remove_job_files', lambda *args: None)
    monkeypatch.setattr(tasks.merge_pages_task, 'apply_async', MagicMock())
    monkeypatch.setattr(tasks.merge_pages_task, 'delay', MagicMock())
    def retry(exc=None, **kwargs):
        raise RetryCalled(exc)
    for task in [tasks.convert_page_task, tasks.merge_pages_task]:
        monkeypatch.setattr(task, 'retry', retry)
    staged = []
    monkeypatch.setattr('shared.datalake.service.stage_result', lambda job_id, result, **kw: staged.append(copy.deepcopy(result)))
    monkeypatch.setattr('shared.datalake.service.enqueue_export', MagicMock())
    options = document_options({'formats': ['markdown', 'html', 'json', 'txt'], 'output_format': 'html',
        'page_range': [2, 3], 'pipeline': {'force_backend_text': True},
        'export_options': {'markdown': {'image_mode': 'referenced'}, 'html': {'image_mode': 'referenced'}}})
    with session_local() as db:
        parent = Job(id='native-parent', filename='report.pdf', status=JobStatus.PROCESSING, total_pages=2)
        db.add(parent)
        save_configuration(db, parent, operation='document', provider='docling', options=options)
        for number in [2, 3]:
            db.add(Page(job_id=parent.id, page_number=number, page_job_id=f'page-{number}', status=JobStatus.PENDING))
            fake_redis.add_child_job(parent.id, 'page', f'page-{number}')
        db.commit()
    fake_redis.set_job_pages('native-parent', 2)
    received = []
    def convert(path, chosen):
        received.append(copy.deepcopy(chosen))
        document = make_document()
        document.texts[1].text = f'Source page {path.stem}'
        result = document_outputs.export_document(document, chosen, tmp_path / (path.stem + '-assets'))
        result['metadata'] = {'words': 3, 'pages': 1}
        return result
    converter = SimpleNamespace(convert_to_markdown=convert)
    monkeypatch.setattr(tasks, 'get_converter', lambda **kwargs: converter)
    def page(number):
        source = tmp_path / f'{number}.pdf'; source.write_bytes(b'PDF fixture')
        return run_task(tasks.convert_page_task, page_job_id=f'page-{number}', parent_job_id='native-parent',
            page_number=number, page_file_path=str(source), options=options)
    return SimpleNamespace(page=page, redis=fake_redis, objects=objects, db=session_local,
                           options=options, received=received, staged=staged, storage=storage)


def test_native_page_options_and_merge_survive_total_cache_loss(pipeline):
    original = copy.deepcopy(pipeline.options)
    pipeline.page(2); pipeline.page(3)
    assert pipeline.options == original
    for received in pipeline.received:
        assert received['document_options']['page_range'] is None
        assert received['document_options']['pipeline']['force_backend_text'] is True
        assert received['document_options']['output_format'] == 'html'
    pipeline.redis.client.flushall()
    result = run_task(tasks.merge_pages_task, merge_job_id='merge-native', parent_job_id='native-parent')
    assert result['pages_merged'] == 2
    merged = pipeline.staged[-1]
    assert set(merged['exports']) == {'markdown', 'html', 'json', 'txt'}
    assert 'Source page 2' in merged['exports']['txt'] and 'Source page 3' in merged['exports']['txt']
    assert set(json.loads(merged['exports']['json'])['pages']) == {'2', '3'}
    assert merged['metadata']['source_page_numbers'] == [2, 3]
    assert merged['metadata']['configuration'] == original['document_options']
    assert merged['assets'] and '/jobs/native-parent/assets/' in merged['exports']['html']
    assert '/pages/2/assets/' not in merged['exports']['html']
    for asset in merged['assets']:
        assert pipeline.objects['results', asset['object_name']]
    with pipeline.db() as db:
        job = db.get(Job, 'native-parent')
        assert job.status == JobStatus.COMPLETED and job.minio_result_path
        saved = json.loads(pipeline.objects['results', job.minio_result_path])
        assert saved['exports'] == merged['exports']


def test_missing_native_page_retries_merge_instead_of_publishing_partial_result(pipeline):
    pipeline.page(2); pipeline.page(3)
    pipeline.redis.client.flushall()
    del pipeline.objects['results', document_outputs.result_object('native-parent', 3)]
    with pytest.raises(RetryCalled, match='durável da página 3'):
        run_task(tasks.merge_pages_task, merge_job_id='merge-native', parent_job_id='native-parent')
    assert pipeline.staged == []
    with pipeline.db() as db:
        assert db.get(Job, 'native-parent').status == JobStatus.FAILED


def test_native_page_persistence_failure_does_not_complete_page(pipeline):
    pipeline.storage.upload_file.side_effect = lambda **kwargs: False
    with pytest.raises(RetryCalled, match='not persisted'):
        pipeline.page(2)
    with pipeline.db() as db:
        page = db.query(Page).filter_by(job_id='native-parent', page_number=2).one()
        assert page.status == JobStatus.FAILED
    assert pipeline.redis.get_job_result('page-2') is None


def test_manual_page_retry_restores_saved_document_options(env, monkeypatch):
    from api import routes
    from sqlalchemy.orm import sessionmaker
    from tests.test_document_capabilities import upload
    from tests.test_upload_projects import jwt
    options = {'formats': ['markdown', 'json', 'html'], 'output_format': 'json', 'page_range': [2, 3],
               'pipeline': {'force_backend_text': True}, 'export_options': {'html': {'split_page_view': True}}}
    created = upload(env, options)
    assert created.status_code == 200
    job_id = created.json()['job_id']
    env.db.add(Page(job_id=job_id, page_number=2, page_job_id='failed-page', status=JobStatus.FAILED, retry_count=0))
    env.db.commit()
    monkeypatch.setattr(routes, 'SessionLocal', sessionmaker(bind=env.db.bind))
    submitted = []
    monkeypatch.setattr(tasks.process_page, 'delay', lambda **kwargs: submitted.append(kwargs))
    response = env.client.post(f'/jobs/{job_id}/pages/2/retry', headers=jwt())
    assert response.status_code == 200, response.text
    saved = env.db.get(Job, job_id).configuration_row.options
    assert submitted[0]['options'] == saved
    assert submitted[0]['options']['document_options']['output_format'] == 'json'
    assert submitted[0]['page_number'] == 2
