"""Document configuration reaches every source and survives durable result reads."""
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from api import routes
from shared.document_capabilities import DocumentOptions, document_options, native_catalog
from shared.job_configuration import job_configuration
from shared.models import Job, JobConfiguration, JobStatus, Page
from tests.test_upload_projects import db, env, jwt  # noqa: F401
from workers.document_outputs import export_document, store_document_result


def upload(env, options=None, endpoint='/upload', **extra):
    return env.client.post(endpoint, headers=jwt(), files={'file': ('document.pdf', b'%PDF-fixture', 'application/pdf')},
        data={'project': 'Document checks', **({'source_type': 'file'} if endpoint == '/convert' else {}),
              **({'conversion_options': json.dumps(options)} if options is not None else {}), **extra})


def test_catalog_matches_snapshot_without_loading_torch(env):
    assert env.client.get('/documents/capabilities').status_code == 401
    response = env.client.get('/documents/capabilities', headers=jwt())
    assert response.status_code == 200
    catalog = response.json()
    assert len(catalog['pipeline_schema']['properties']) == 30
    assert set(catalog['exports']) == {'markdown', 'json', 'html', 'txt', 'doclang', 'doctags', 'document_tokens', 'element_tree', 'vtt'}
    assert all(catalog['pipeline_schema']['properties'][name]['readOnly'] for name in catalog['server_managed'])
    assert set(catalog['image_extensions']) == {'jpg', 'jpeg', 'png', 'tif', 'tiff', 'bmp', 'webp'}


@pytest.mark.parametrize('endpoint', ['/upload', '/convert'])
def test_unsupported_docling_image_format_fails_before_queue(env, endpoint):
    response = env.client.post(endpoint, headers=jwt(), files={'file': ('scan.gif', b'GIF89a', 'image/gif')},
        data={'project': 'Image document', **({'source_type': 'file'} if endpoint == '/convert' else {})})
    assert response.status_code == 422 and 'image_extensions' in response.json()['detail']
    assert not env.enqueued and env.db.query(Job).count() == 0 and list(env.tmp.iterdir()) == []


@pytest.mark.parametrize('options', [
    {'pipeline': {'unknown': True}}, {'pipeline': {'do_ocr': 'false'}}, {'pipeline': {'queue_max_size': 0}},
    {'pipeline': {'images_scale': 0}}, {'pipeline': {'document_timeout': 100000}},
    {'pipeline': {'ocr_options': {'kind': 'unknown'}}}, {'pipeline': {'ocr_options': {'kind': 'tesseract', 'tesseract_cmd': 'python'}}},
    {'pipeline': {'enable_remote_services': True}}, {'pipeline': {'artifacts_path': '/tmp'}},
    {'pipeline': {'ocr_options': {'kind': 'kserve_v2_ocr'}}},
    {'pipeline': {'picture_description_options': {'kind': 'api'}}},
    {'formats': ['html']}, {'formats': []}, {'formats': ['markdown', 'markdown']},
    {'export_options': {'markdown': {'unknown': True}}}, {'export_options': {'markdown': {'image_dir': '/tmp'}}},
    {'page_range': [3, 1]}, {'page_range': [0, 1]}, {'max_num_pages': 0},
])
def test_invalid_configuration_has_no_side_effects(env, options):
    response = upload(env, options)
    assert response.status_code == 422, response.text
    assert env.db.query(Job).count() == 0 and env.db.query(JobConfiguration).count() == 0
    assert env.enqueued == [] and list(env.tmp.iterdir()) == []


@pytest.mark.parametrize('endpoint', ['/upload', '/convert'])
def test_effective_options_are_durable_and_control_deduplication(env, endpoint):
    options = {'pipeline': {'force_backend_text': True, 'ocr_options': {'kind': 'tesseract', 'lang': ['eng']}},
               'formats': ['markdown', 'html', 'json'], 'output_format': 'html', 'page_range': [2, 3],
               'export_options': {'markdown': {'compact_tables': True}, 'html': {'split_page_view': True}}}
    first = upload(env, options, endpoint=endpoint)
    assert first.status_code == 200, first.text
    job_id = first.json()['job_id']
    persisted = job_configuration(env.db.get(Job, job_id))
    assert persisted['provider'] == 'docling' and persisted['model'] == native_catalog()['docling_version']
    assert persisted['options']['document_options']['pipeline']['force_backend_text'] is True
    assert persisted['options']['document_options']['pipeline']['ocr_options']['kind'] == 'tesseract'
    assert env.enqueued[0]['options'] == persisted['options']
    assert persisted['options']['processing_mode'] == 'document'
    repeated = upload(env, options, endpoint=endpoint)
    assert repeated.json()['job_id'] == job_id and len(env.enqueued) == 1
    changed = upload(env, {**options, 'output_format': 'json'}, endpoint=endpoint)
    assert changed.json()['job_id'] != job_id and len(env.enqueued) == 2
    env.db.expire_all()
    response = env.client.get('/jobs/' + job_id, headers=jwt())
    assert response.status_code == 200 and response.json()['configuration'] == persisted


@pytest.mark.parametrize('source_type', ['url', 'gdrive', 'dropbox'])
def test_source_downloads_use_the_same_document_configuration(env, source_type):
    response = env.client.post('/convert', headers={**jwt(), 'X-Source-Token': 'test-provider-token'}, data={
        'source_type': source_type, 'source': 'https://example.com/document.pdf', 'project': 'Sources',
        'docling_preset': 'quality', 'conversion_options': json.dumps({'pipeline': {'force_backend_text': True}})})
    assert response.status_code == 200, response.text
    queued = env.enqueued[0]
    assert queued['options']['document_options']['pipeline']['do_ocr'] is True
    assert queued['options']['document_options']['pipeline']['force_backend_text'] is True
    assert 'test-provider-token' not in json.dumps(queued)


def make_document():
    from docling_core.types.doc import DoclingDocument, DocItemLabel, ImageRef, Size
    from PIL import Image
    document = DoclingDocument(name='test-document')
    document.add_page(page_no=1, size=Size(width=600, height=800))
    document.add_text(label=DocItemLabel.TITLE, text='Native document title')
    document.add_text(label=DocItemLabel.TEXT, text='Native document contents.')
    document.add_picture(image=ImageRef.from_pil(Image.new('RGB', (30, 20), 'red'), dpi=72))
    return document


def test_all_nine_exports_execute_on_a_native_document(tmp_path):
    options = document_options({'formats': list(native_catalog()['exports']), 'export_options': {
        'markdown': {'image_mode': 'referenced'}, 'html': {'image_mode': 'referenced'}}})
    result = export_document(make_document(), {**options, '_asset_url_prefix': '/jobs/fixture/assets'}, tmp_path / 'assets')
    assert set(result['exports']) == set(native_catalog()['exports'])
    assert 'Native document contents' in result['exports']['txt']
    assert json.loads(result['exports']['json'])['name'] == 'test-document'
    assert result['assets'] and '/jobs/fixture/assets/image_' in result['markdown']
    assert str(tmp_path) not in result['markdown']
    assert 'data:image/png;base64,' in json.dumps(result['document'])


def test_partial_durable_write_cannot_complete_a_document(tmp_path, monkeypatch):
    result = export_document(make_document(), {'_asset_url_prefix': '/jobs/fixture/assets'}, tmp_path)
    storage = MagicMock(); storage.upload_file.return_value = False
    monkeypatch.setattr('workers.document_outputs.get_minio_client', lambda: storage)
    with pytest.raises(RuntimeError, match='not persisted'):
        store_document_result('fixture', result)


def test_default_format_and_page_exports_survive_expired_cache(env, monkeypatch, fake_redis):
    created = upload(env, {'formats': ['markdown', 'html', 'json'], 'output_format': 'html'})
    job_id = created.json()['job_id']
    job = env.db.get(Job, job_id); job.status = JobStatus.COMPLETED; job.completed_at = datetime.utcnow()
    env.db.add(Page(job_id=job_id, page_number=2, page_job_id='native-page-job', status=JobStatus.COMPLETED))
    env.db.commit(); fake_redis.client.flushall()
    result = {'markdown': '# Saved', 'exports': {'markdown': '# Saved', 'html': '<h1>Saved</h1>', 'json': '{"name":"saved"}'},
              'metadata': {'format': 'pdf', 'size_bytes': 10, 'provider': 'docling', 'output_format': 'html', 'available_formats': ['markdown', 'html', 'json']}}
    storage = MagicMock(); storage.download_file.return_value = json.dumps(result).encode()
    monkeypatch.setattr(routes, 'get_minio_client', lambda: storage)
    monkeypatch.setattr(routes, 'get_es_client', MagicMock(side_effect=AssertionError('Durable reads do not need search')))
    base = '/jobs/' + job_id
    response = env.client.get(base + '/result', headers=jwt())
    assert response.status_code == 200 and response.headers['content-type'].startswith('text/html')
    assert response.text == '<h1>Saved</h1>'
    envelope = env.client.get(base + '/result?format=markdown', headers=jwt()).json()
    assert envelope['result']['exports'] == result['exports']
    assert envelope['result']['metadata']['output_format'] == 'html'
    assert env.client.get(base + '/pages/2/result?format=json', headers=jwt()).json() == {'name': 'saved'}
    assert env.client.get(base + '/pages/2/result?format=doclang', headers=jwt()).status_code == 422
    assert env.client.get(base + '/result', headers=jwt('user-bob')).status_code == 404


def test_private_asset_requires_manifest_and_owner(env, monkeypatch):
    created = upload(env); job_id = created.json()['job_id']; name = 'image_000000_abc123.png'
    env.db.get(Job, job_id).status = JobStatus.COMPLETED; env.db.commit()
    storage = MagicMock(); storage.download_file.side_effect = [json.dumps({'assets': [
        {'name': name, 'object_name': f'results/{job_id}/assets/{name}'}]}).encode(), b'PNG']
    monkeypatch.setattr(routes, 'get_minio_client', lambda: storage)
    base = f'/jobs/{job_id}/assets/{name}'
    assert env.client.get(base).status_code == 401
    assert env.client.get(base, headers=jwt('user-bob')).status_code == 404
    assert storage.download_file.call_count == 0
    response = env.client.get(base, headers=jwt())
    assert response.status_code == 200 and response.content == b'PNG'
    assert env.client.get(f'/jobs/{job_id}/assets/arbitrary.png', headers=jwt()).status_code == 404


def test_concrete_engine_options_and_partial_model_defaults_are_preserved():
    options = document_options({'pipeline': {
        'picture_description_options': {'prompt': 'Explain this figure', 'engine_options': {'prefer_vllm': True}},
        'picture_classification_options': {'engine_options': {'compile_model': False}},
    }})['document_options']['pipeline']
    assert options['picture_description_options']['engine_options']['engine_type'] == 'auto_inline'
    assert options['picture_description_options']['engine_options']['prefer_vllm'] is True
    assert options['picture_description_options']['model_spec']['default_repo_id']
    assert options['picture_classification_options']['engine_options']['compile_model'] is False
    with pytest.raises(ValueError):
        document_options({'pipeline': {'picture_description_options': {'engine_options': {'invented_control': True}}}})


def test_known_missing_ocr_is_rejected_before_upload(env, fake_redis):
    fake_redis.client.hset('engines:local:document_conversion:test-worker', mapping={
        'document_readiness': json.dumps({'catalog_matches': True, 'ocr_dependencies': {'auto': True, 'ocrmac': False}})})
    response = upload(env, {'pipeline': {'do_ocr': True, 'ocr_options': {'kind': 'ocrmac'}}})
    assert response.status_code == 422 and env.enqueued == []
    assert env.db.query(Job).count() == 0


@pytest.mark.parametrize('pipeline', [
    {'do_picture_description': True, 'picture_description_options': {'engine_options': {'engine_type': 'vllm'}}},
    {'do_formula_enrichment': True, 'code_formula_options': {'engine_options': {'engine_type': 'mlx'}}},
    {'do_code_enrichment': True, 'code_formula_options': {'engine_options': {'engine_type': 'transformers', 'quantized': True}}},
    {'do_picture_classification': True, 'picture_classification_options': {'engine_options': {'engine_type': 'onnxruntime'}}},
])
@pytest.mark.parametrize('endpoint', ['/upload', '/convert'])
def test_missing_enrichment_dependencies_rejected_before_upload(env, fake_redis, pipeline, endpoint):
    fake_redis.client.hset('engines:local:document_conversion:test-worker', mapping={
        'document_readiness': json.dumps({'catalog_matches': True, 'enrichment_dependencies': {
            'auto_inline': True, 'transformers': True, 'vllm': False, 'mlx': False,
            'bitsandbytes': False, 'onnxruntime': False}})})
    response = upload(env, {'pipeline': pipeline}, endpoint)
    assert response.status_code == 422 and 'enriquecimento' in response.json()['detail'], response.text
    assert env.enqueued == [] and env.db.query(Job).count() == 0 and list(env.tmp.iterdir()) == []


def test_missing_enrichment_catalog_disables_only_known_unavailable_engines(env, fake_redis):
    fake_redis.client.hset('engines:local:document_conversion:test-worker', mapping={
        'document_readiness': json.dumps({'catalog_matches': True, 'enrichment_dependencies': {
            'auto_inline': True, 'transformers': True, 'vllm': False, 'mlx': False, 'bitsandbytes': False}})})
    definitions = env.client.get('/documents/capabilities', headers=jwt()).json()['pipeline_schema']['$defs']
    assert definitions['MlxVlmEngineOptions']['x-unavailable-reason']
    assert definitions['VllmVlmEngineOptions']['x-unavailable-reason']
    assert 'x-unavailable-reason' not in definitions['AutoInlineVlmEngineOptions']
    assert 'x-unavailable-reason' not in definitions['OnnxRuntimeImageClassificationEngineOptions']
    assert definitions['TransformersVlmEngineOptions']['properties']['quantized']['enum'] == [False]


def test_unused_unavailable_engine_is_preserved_without_rejecting_conversion(env, fake_redis):
    fake_redis.client.hset('engines:local:document_conversion:test-worker', mapping={
        'document_readiness': json.dumps({'catalog_matches': True, 'enrichment_dependencies': {'vllm': False}})})
    response = upload(env, {'pipeline': {'do_picture_description': False,
        'picture_description_options': {'engine_options': {'engine_type': 'vllm'}}}})
    assert response.status_code == 200 and len(env.enqueued) == 1


def test_enrichment_validation_accepts_legacy_and_capable_workers():
    from shared.document_capabilities import missing_enrichment_dependencies
    pipeline = document_options({'pipeline': {'do_picture_description': True,
        'picture_description_options': {'engine_options': {'engine_type': 'vllm'}}}})['document_options']['pipeline']
    unavailable = {'enrichment_dependencies': {'vllm': False}}
    assert missing_enrichment_dependencies(pipeline, [unavailable]) == ['vllm']
    assert missing_enrichment_dependencies(pipeline, [unavailable, {}]) == []
    assert missing_enrichment_dependencies(pipeline, [unavailable, {'enrichment_dependencies': {'vllm': True}}]) == []


def test_cancelled_configuration_is_never_reused(env):
    first = upload(env); row = env.db.get(Job, first.json()['job_id'])
    row.status = JobStatus.CANCELLED; env.db.commit()
    second = upload(env)
    assert second.status_code == 200 and second.json()['job_id'] != row.id


def test_converter_wrapper_passes_limits_and_preserves_native_outputs(tmp_path):
    from workers.converter import DoclingConverter
    path = tmp_path / 'document.pdf'; path.write_bytes(b'%PDF-fixture')
    native = MagicMock(); native.convert.return_value = SimpleNamespace(document=make_document())
    converter = DoclingConverter.__new__(DoclingConverter); converter.converter = native
    options = document_options({'formats': ['markdown', 'html', 'json'], 'page_range': [1, 1], 'max_num_pages': 5})
    result = converter.convert_to_markdown(path, {**options, '_asset_url_prefix': '/jobs/fixture/assets'})
    assert native.convert.call_args.kwargs == {'page_range': [1, 1], 'max_num_pages': 5, 'raises_on_error': True}
    assert result['metadata']['provider'] == 'docling' and result['metadata']['pages'] == 1
    assert set(result['exports']) == {'markdown', 'html', 'json'}


def test_concatenated_document_filters_use_original_page_numbers(tmp_path):
    from docling_core.types.doc import DoclingDocument
    from workers.document_outputs import preserve_source_page_numbers
    document = preserve_source_page_numbers(DoclingDocument.concatenate([make_document(), make_document()]), [2, 3])
    assert set(document.pages) == {2, 3}
    result = export_document(document, document_options({'formats': ['markdown', 'json']}), tmp_path)
    assert set(json.loads(result['exports']['json'])['pages']) == {'2', '3'}
