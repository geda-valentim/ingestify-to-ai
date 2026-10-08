"""Every published operation sits in a declared Swagger group and has a summary."""
from api.main import app
from api.openapi_docs import OPENAPI_TAGS

METHODS = {'get', 'post', 'put', 'patch', 'delete', 'options', 'head', 'trace'}


def _operations(schema):
    return [(method.upper(), path, op) for path, item in schema['paths'].items()
            for method, op in item.items() if method in METHODS]


def test_every_operation_has_a_declared_tag_and_a_summary():
    schema = app.openapi()
    declared = [tag['name'] for tag in schema['tags']]
    assert declared == [tag['name'] for tag in OPENAPI_TAGS]
    assert len(set(declared)) == len(declared)
    assert all(tag['description'].strip() for tag in schema['tags'])
    problems = []
    for method, path, op in _operations(schema):
        tags = op.get('tags') or []
        if not tags or any(tag not in declared for tag in tags):
            problems.append(f'{method} {path}: tags {tags}')
        if not (op.get('summary') or '').strip():
            problems.append(f'{method} {path}: no summary')
    assert not problems, '\n'.join(problems)


def test_every_declared_tag_is_used():
    schema = app.openapi()
    used = {tag for _, _, op in _operations(schema) for tag in op.get('tags', [])}
    assert {tag['name'] for tag in schema['tags']} <= used


def test_info_and_security_schemes():
    schema = app.openapi()
    assert schema['info']['version'] == app.version
    description = schema['info']['description']
    for topic in ('purge_source', 'GET /auth/setup', 'ROOT_SETUP_TOKEN', 'Idempotency-Key',
                  'next_steps', 'partial', 'queued', 'DELETE /jobs/{job_id}/source', 'x-access'):
        assert topic in description, topic
    schemes = schema['components']['securitySchemes']
    assert schemes['bearerAuth'] == {**schemes['bearerAuth'], 'type': 'http', 'scheme': 'bearer'}
    assert schemes['apiKeyAuth'] == {**schemes['apiKeyAuth'], 'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'}


def test_swagger_and_redoc_load_behind_root_path():
    from fastapi.testclient import TestClient
    client = TestClient(app, root_path='/api')
    page = client.get('/docs')
    assert page.status_code == 200 and '/api/openapi.json' in page.text
    assert client.get('/redoc').status_code == 200
    assert client.get('/openapi.json').json()['info']['title'] == 'Ingestify API'
