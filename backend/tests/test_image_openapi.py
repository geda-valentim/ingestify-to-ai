"""Published image schemas and migrations must describe the executable API."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_published_schema_matches_live_app_and_generator():
    from api.main import app
    schema = app.openapi()
    published = json.loads((ROOT/'frontend/docs/doc2md_openapi.json').read_text())
    assert published == schema
    for path in ('/images/faces', '/images/faces/upload', '/images/analyze', '/images/analyze/upload'):
        operation = schema['paths'][path]['post']
        assert operation['x-access'] == 'user'
        assert {'409','410'} <= set(operation['responses'])
    assert schema['components']['schemas']['ImageFullOptions']['properties']['profile']['default'] == 'image-full-v1'
    assert schema['components']['schemas']['FaceAnalysisResult']['properties']['schema_version']['const'] == 'face-result-v1'
    assert len(schema['components']['schemas']['ImageAnalyzeOptions']['properties']['task']['x-task-catalog']) == 15
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_api_docs.py'),'--check'],check=True,capture_output=True,env=os.environ.copy())


def test_facial_migrations_have_one_head_on_current_main_chain():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(ROOT/'alembic.ini'))
    config.set_main_option('script_location', str(ROOT/'alembic'))
    scripts = ScriptDirectory.from_config(config)
    # The IAM bindings branch (spec 0014) keeps its original parent and is joined to
    # the facial chain by a merge revision, so DBs stamped a1c40014e7b2 still upgrade.
    # image_analysis_submissions.attempt follows spec 0019 as the single head.
    # jobs source bookkeeping + uq_pages_job_page follow it; the conversion image
    # assets columns follow them as the single head.
    assert scripts.get_heads() == ['c3a70024e5b1']
    assert scripts.get_revision('c3a70024e5b1').down_revision == 'b8f20022e1c4'
    assert scripts.get_revision('b8f20022e1c4').down_revision == 'a7d30021c5e9'
    assert scripts.get_revision('a7d30021c5e9').down_revision == 'f1c90019d3e4'
    # Spec 0019 (users.root_slot) follows spec 0018.
    assert scripts.get_revision('f1c90019d3e4').down_revision == 'd4e80018a2b6'
    # Spec 0018 (engine grants into IAM bindings) follows the merge revision.
    assert scripts.get_revision('d4e80018a2b6').down_revision == '03e70014b8c5'
    assert set(scripts.get_revision('03e70014b8c5').down_revision) == {'02c6000ce6e5', 'a1c40014e7b2'}
    assert scripts.get_revision('a1c40014e7b2').down_revision == 'f0b40009c4d3'
    assert scripts.get_revision('02c6000ce6e5').down_revision == '01b5000bd5d4'
    assert scripts.get_revision('01b5000bd5d4').down_revision == 'f0b40009c4d3'


def test_every_image_route_publishes_purge_source():
    """The external DAG integrates against the contract: purge_source must be in it."""
    from api.main import app
    schema = app.openapi()
    components = schema['components']['schemas']

    def body_properties(path):
        content = schema['paths'][path]['post']['requestBody']['content']
        media = content.get('multipart/form-data') or content['application/json']
        ref = media['schema'].get('$ref')
        if ref:
            return components[ref.rsplit('/', 1)[-1]]['properties']
        # a union body (analyze): every alternative carries it
        alternatives = media['schema'].get('anyOf') or media['schema'].get('oneOf')
        merged = {}
        for alternative in alternatives:
            merged.update(components[alternative['$ref'].rsplit('/', 1)[-1]]['properties'])
        return merged

    for path in ('/images/describe/upload', '/images/ocr/upload', '/images/analyze/upload',
                 '/images/faces/upload', '/images/describe', '/images/ocr', '/images/analyze',
                 '/images/faces'):
        field = body_properties(path)['purge_source']
        assert field['type'] == 'boolean' and field['default'] is False, path
        assert 'DELETE /jobs/{job_id}/source' in field['description'], path
