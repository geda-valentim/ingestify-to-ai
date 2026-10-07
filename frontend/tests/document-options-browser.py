#!/usr/bin/env python3
"""Catalog-driven document settings, exports and recovery after reload."""
import argparse
import base64
import json
import re
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

CATALOG = json.loads((Path(__file__).resolve().parents[2] / 'backend/shared/docling_catalog.json').read_text())
USER = {'id': 'document-test', 'username': 'document-test', 'email': 'document@example.test', 'is_active': True, 'is_admin': False}
PROJECT = {'id': 'document-project', 'name': 'Document checks', 'archived': False, 'folders': []}
JOB = '77777777-7777-4777-8777-777777777777'
CORS = {'access-control-allow-origin': '*', 'access-control-allow-headers': '*'}
PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
ASSET_NAME = 'image_000001_abcdef.png'
ASSET_URL = '/jobs/' + JOB + '/assets/' + ASSET_NAME
MARKDOWN = 'DOCUMENT_RESULT\n\n![Private figure](' + ASSET_URL + ')\n\n![Embedded figure](data:image/png;base64,' + PNG_B64 + ')\n\n[Unsafe link](javascript:alert%281%29)'


def check(browser, url, source):
    context = browser.new_context(viewport={'width': 1440, 'height': 1100})
    auth = json.dumps({'state': {'user': USER, 'token': 'synthetic-document-token'}, 'version': 0})
    context.add_init_script('if (window.top === window) localStorage.setItem("auth-storage", ' + json.dumps(auth) + ');')
    page = context.new_page(); captured, errors, asset_requests = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    configuration = {'operation': 'document', 'provider': 'docling', 'model': CATALOG['docling_version'], 'options': {}}
    def intercept(route):
        request = route.request
        if request.resource_type not in ('fetch', 'xhr'): return route.continue_()
        if request.method == 'OPTIONS': return route.fulfill(status=204, headers=CORS)
        path = urlparse(request.url).path.removeprefix('/api')
        if path == '/auth/me': value = USER
        elif path == ASSET_URL:
            asset_requests.append(request.headers.get('authorization'))
            return route.fulfill(body=base64.b64decode(PNG_B64), content_type='image/png', headers=CORS)
        elif path == '/projects': value = {'projects': [PROJECT]}
        elif path == '/datalakes': value = {'connections': []}
        elif path == '/documents/capabilities':
            schema = json.loads(json.dumps(CATALOG['pipeline_schema']))
            for name in CATALOG['server_managed']: schema['properties'][name]['readOnly'] = True
            for name in ('VllmVlmEngineOptions', 'MlxVlmEngineOptions'):
                schema['$defs'][name]['x-unavailable-reason'] = 'Dependência do engine ausente nos workers ativos'
            value = {'provider': 'docling', 'version': CATALOG['docling_version'], 'core_version': CATALOG['docling_core_version'],
                'pipeline_schema': schema, 'exports': CATALOG['exports'], 'presets': {
                    'fast': {'do_ocr': False}, 'balanced': {'do_ocr': False}, 'quality': {'do_ocr': True}},
                'image_extensions': CATALOG['image_extensions'], 'server_managed': CATALOG['server_managed'], 'restrictions': [], 'workers_running': True, 'worker_prerequisites': []}
        elif path in ('/upload', '/convert') and request.method == 'POST':
            message = BytesParser(policy=default).parsebytes(b'Content-Type: ' + request.headers['content-type'].encode() + b'\r\n\r\n' + request.post_data_buffer)
            parts = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True) for part in message.iter_parts()}
            options = json.loads(parts['conversion_options'])
            assert parts['docling_preset'] == b'quality'
            assert options['pipeline']['force_backend_text'] is True
            assert options['pipeline']['ocr_options']['kind'] == 'tesseract'
            assert options['pipeline']['ocr_options']['lang'] == ['por']
            assert options['page_range'] == ([1, 1] if source == 'image' else [2, 3]) and options['output_format'] == 'html'
            assert options['export_options']['html']['split_page_view'] is True
            assert set(options['formats']) == {'markdown', 'html', 'json'}
            if source == 'url': assert parts['source_type'] == b'url' and parts['source'] == b'https://example.com/document.pdf'
            captured.append(parts); configuration['options'] = {'docling_preset': 'quality', 'document_options': options}
            return route.fulfill(json={'job_id': JOB, 'status': 'queued', 'created_at': '2026-10-06T00:00:00', 'project': PROJECT}, headers=CORS)
        elif path == '/jobs/' + JOB:
            value = {'job_id': JOB, 'type': 'main', 'kind': 'document', 'status': 'completed', 'progress': 100,
                'created_at': '2026-10-06T00:00:00', 'name': 'document.pdf', 'configuration': configuration}
        elif path == '/jobs/' + JOB + '/pages': value = {'pages': [], 'total_pages': 0}
        elif path == '/jobs/' + JOB + '/result':
            value = {'job_id': JOB, 'status': 'completed', 'result': {'markdown': MARKDOWN,
                'metadata': {'format': 'pdf', 'size_bytes': 100, 'provider': 'docling', 'output_format': 'html', 'available_formats': ['markdown', 'html', 'json']},
                'assets': [{'name': ASSET_NAME, 'url': ASSET_URL}],
                'exports': {'markdown': MARKDOWN, 'html': '<h1>HTML_RESULT</h1><img alt="HTML figure" src="' + ASSET_URL + '">', 'json': '{"name":"JSON_RESULT"}'}}}
        else: return route.fulfill(status=404, json={'detail': 'Unavailable in fixture'}, headers=CORS)
        route.fulfill(json=value, headers=CORS)
    page.route('**/*', intercept)
    try:
        page.goto(url.rstrip('/') + '/convert?project_id=' + PROJECT['id'], wait_until='domcontentloaded', timeout=45000)
        if source == 'image':
            page.locator('input[type="file"]').set_input_files({'name': 'scan.gif', 'mimeType': 'image/gif', 'buffer': base64.b64decode(PNG_B64)})
            expect(page.get_by_label('Modelo para a imagem').locator('option[value="docling"]')).to_be_disabled()
            page.get_by_role('button', name='Remove file').click()
            page.locator('input[type="file"]').set_input_files({'name': 'scan.png', 'mimeType': 'image/png', 'buffer': base64.b64decode(PNG_B64)})
            page.get_by_label('Modelo para a imagem').select_option('docling')
        elif source == 'file': page.locator('input[type="file"]').set_input_files({'name': 'document.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-fixture'})
        else:
            page.get_by_role('tab', name='URL', exact=True).click(); page.get_by_label('Document URL').fill('https://example.com/document.pdf')
        page.get_by_text('Opções de documentos · Docling ' + CATALOG['docling_version'], exact=True).click()
        page.get_by_label('Preset de conversão').select_option('quality')
        page.get_by_text('OCR, tabelas, imagens e enriquecimentos', exact=True).click()
        page.get_by_label('Force Backend Text', exact=True).select_option('true')
        page.get_by_label('ocr_options engine', exact=True).select_option('tesseract')
        page.get_by_label('Lang', exact=True).fill('["por"]')
        description = page.get_by_text('picture description options', exact=True).locator('..')
        description.get_by_role('button', name='Configurar picture description options', exact=True).click()
        description.get_by_role('button', name='Configurar engine options', exact=True).click()
        engine = description.get_by_label('engine_options engine', exact=True)
        expect(engine.locator('option[value="vllm"]')).to_be_disabled()
        expect(engine.locator('option[value="mlx"]')).to_be_disabled()
        expect(engine.locator('option[value="transformers"]')).to_be_enabled()
        engine.locator('..').get_by_role('button', name='Restaurar padrões', exact=True).click()
        description.get_by_role('button', name='Restaurar padrões', exact=True).click()
        page.get_by_role('checkbox', name='HTML', exact=True).check()
        page.get_by_role('checkbox', name='JSON', exact=True).check()
        page.get_by_label('Formato padrão do resultado').select_option('html')
        page.get_by_text('Parâmetros de HTML', exact=True).click()
        page.get_by_label('Split Page View', exact=True).select_option('true')
        page.get_by_text('Páginas e limites', exact=True).click()
        interval = page.get_by_label('Intervalo de páginas [primeira, última]')
        interval.fill('[2,')
        submit = page.get_by_role('button', name='Processar arquivo' if source in ('file', 'image') else 'Convert from URL', exact=True)
        expect(submit).to_be_disabled(); interval.fill('[1,1]' if source == 'image' else '[2,3]'); expect(submit).to_be_enabled(); submit.click()
        expect(page.get_by_text('Configuração solicitada', exact=True)).to_be_visible(timeout=45000)
        expect(page.get_by_label('Formato do documento')).to_have_value('html')
        html_image = page.frame_locator('iframe[title="HTML do documento"]').get_by_alt_text('HTML figure')
        expect(html_image).to_have_js_property('naturalWidth', 1)
        page.get_by_label('Formato do documento').select_option('markdown')
        figure = page.get_by_alt_text('Private figure')
        expect(figure).to_have_attribute('src', re.compile(r'^blob:'))
        expect(figure).to_have_js_property('naturalWidth', 1)
        expect(page.get_by_alt_text('Embedded figure')).to_have_js_property('naturalWidth', 1)
        assert not page.get_by_role('link', name='Unsafe link').get_attribute('href')
        page.get_by_label('Formato do documento').select_option('json')
        expect(page.get_by_role('button', name='Download .json', exact=True)).to_be_visible()
        page.reload(wait_until='domcontentloaded', timeout=45000)
        expect(page.get_by_label('Formato do documento')).to_have_value('html', timeout=45000)
        expect(page.frame_locator('iframe[title="HTML do documento"]').get_by_alt_text('HTML figure')).to_have_js_property('naturalWidth', 1, timeout=20000)
        assert asset_requests and set(asset_requests) == {'Bearer synthetic-document-token'}, asset_requests
        assert len(captured) == 1 and not errors, errors
        print('PASS document settings, OCR selection, formats, authenticated/embedded images, invalid JSON, request and F5:', source, flush=True)
    except Exception:
        print('Document preview failure:', source, 'asset requests=', len(asset_requests),
            'alerts=', page.get_by_role('alert').all_text_contents(), 'errors=', errors, flush=True)
        raise
    finally: context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--url', default='http://localhost:3001'); parser.add_argument('--chromium'); args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
        for source in ('file', 'url', 'image'): check(browser, args.url, source)
        browser.close()
