"""Publish the actual authorization and wire formats, and detect stale docs."""
import importlib.util
import json
from pathlib import Path

import pytest

from api.main import app
from shared.transcripts import TRANSCRIPT_CONTENT_TYPES

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def schema():
    return app.openapi()


@pytest.mark.parametrize('path,method', [
    ('/admin/engines', 'post'),
    ('/admin/engines/{engine_id}/runtime-profile', 'put'),
    ('/admin/engines/{engine_id}/activate', 'post'),
    ('/admin/routing/{feature}', 'put'),
])
def test_admin_session_contract_does_not_advertise_api_keys(schema, path, method):
    operation = schema['paths'][path][method]
    assert operation['security'] == [{'bearerAuth': []}]
    assert operation['x-access'] == 'admin-session'


def test_host_routes_require_the_machine_identity_in_swagger(schema):
    assert schema['components']['securitySchemes']['engineHostAuth']['name'] == 'X-Engine-Host-Token'
    host_routes = {path: ops for path, ops in schema['paths'].items() if path.startswith('/internal/engine-hosts/')}
    assert host_routes
    for ops in host_routes.values():
        for operation in ops.values():
            assert operation['security'] == [{'engineHostAuth': []}]
            assert operation['x-access'] == 'engine-host'
    assert schema['paths']['/health']['get']['x-access'] == 'public'
    assert schema['paths']['/admin/settings']['get']['x-access'] == 'admin'


def test_response_types_match_native_formats_and_streams(schema):
    responses = schema['paths']['/jobs/{job_id}/result']['get']['responses']['200']['content']
    assert {value.split(';')[0] for value in TRANSCRIPT_CONTENT_TYPES.values()} <= set(responses)
    assert 'anyOf' in responses['application/json']['schema']
    pdf = schema['paths']['/jobs/{job_id}/pages/{page_number}/pdf/content']['get']['responses']['200']['content']
    assert set(pdf) == {'application/pdf'} and pdf['application/pdf']['schema']['format'] == 'binary'
    sse = schema['paths']['/admin/engine-operations/{operation_id}/stream']['get']['responses']['200']['content']
    assert set(sse) == {'text/event-stream'}


def test_get_or_add_statuses_and_websocket_are_documented(schema):
    for path in ['/projects', '/projects/{project_id}/folders']:
        assert {'200', '201'} <= set(schema['paths'][path]['post']['responses'])
    assert [ws['path'] for ws in schema['x-websockets']] == ['/transcribe/live/sessions/{job_id}/stream']
    assert 'authenticate' in schema['x-websockets'][0]['authentication']
    assert 'offset_samples' in schema['x-websockets'][0]['protocol']


def test_reference_and_snapshot_are_generated_from_all_routes(schema):
    generator_path = ROOT / 'scripts/generate_api_docs.py'
    assert generator_path.exists(), 'Copy scripts alongside backend tests for documentation verification'
    spec = importlib.util.spec_from_file_location('generate_api_docs', generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reference = ROOT / 'docs/api-reference.md'
    reference_text = reference.read_text()
    assert reference_text == module.render_reference(schema), 'Run scripts/generate_api_docs.py'
    assert json.loads((ROOT / 'frontend/docs/doc2md_openapi.json').read_text()) == schema
    for path, method, operation in module.operations(schema):
        assert operation['x-access'] in module.ACCESS
        assert f'### {method.upper()} {path}' in reference_text


@pytest.mark.parametrize('path', ['/admin/engines/{engine_id}/runtime-profile', '/admin/engine-operations/{operation_id}/stream'])
def test_scoped_engine_reads_require_jwt_without_advertising_api_keys(schema, path):
    operation = schema['paths'][path]['get']
    assert operation['security'] == [{'bearerAuth': []}]
    assert operation['x-access'] == 'jwt'


def test_full_image_contract_advertises_modes_key_and_terminal_results(schema):
    for path in ('/images/analyze', '/images/analyze/upload'):
        operation = schema['paths'][path]['post']
        assert any(p['in'] == 'header' and p['name'].lower() == 'idempotency-key' for p in operation['parameters'])
        assert {'202', '409', '410'} <= set(operation['responses'])
    assert '/images/{job_id}/cancel' in schema['paths']
    assert schema['components']['schemas']['ImageFullAnalyzeRequest']['properties']['mode']['const'] == 'full'
    assert schema['components']['schemas']['ImageFullOptions']['properties']['deadline_seconds']['maximum'] == 900
    assert 'partial' in schema['components']['schemas']['JobStatus']['enum']
