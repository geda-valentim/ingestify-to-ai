#!/usr/bin/env python3
"""Document image options on /convert (every tab) and the job page's Images tab.

Every API request is intercepted. Run against a built frontend:
python tests/convert-images-browser.py --url http://localhost:3108 --chromium /path/to/chrome
"""
import argparse
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse
import zipfile
from playwright.sync_api import sync_playwright, expect

spec = importlib.util.spec_from_file_location('native_vision', Path(__file__).with_name('vision-analysis-browser.py'))
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
USER, PROJECT, JOB, PNG, CORS = fixture.USER, fixture.PROJECT, fixture.JOB, fixture.PNG, fixture.CORS
PDF = b'%PDF-1.4\n%fixture\n'
ASSETS = [
    {'name': 'p0001-page-9b1c0d2e3f4a.png', 'kind': 'page', 'page': 1, 'bbox': None, 'sha256': '9b1c', 'mime': 'image/png',
     'width': 1275, 'height': 1650, 'size_bytes': len(PNG), 'url': f'/jobs/{JOB}/assets/p0001-page-9b1c0d2e3f4a.png'},
    {'name': 'p0001-img01-3f2a9c1b7d4e.png', 'kind': 'picture', 'page': 1,
     'bbox': {'l': 1, 't': 2, 'r': 3, 'b': 4, 'coord_origin': 'TOPLEFT'}, 'sha256': '3f2a', 'mime': 'image/png',
     'width': 601, 'height': 453, 'size_bytes': len(PNG), 'url': f'/jobs/{JOB}/assets/p0001-img01-3f2a9c1b7d4e.png'},
]


def form_parts(req):
    message = BytesParser(policy=default).parsebytes(
        b'Content-Type: ' + req.headers['content-type'].encode() + b'\r\n\r\n' + req.post_data_buffer)
    return {p.get_param('name', header='content-disposition'): p.get_payload(decode=True) for p in message.iter_parts()}


def check(browser, url, viewport):
    context = browser.new_context(viewport=viewport, accept_downloads=True)
    auth = json.dumps({'state': {'user': USER, 'token': 'synthetic-assets-token'}, 'version': 0})
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(auth) + ');')
    page = context.new_page(); errors = []; sent = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    state = {'assets_available': True, 'deleted': False}
    expire_at = (datetime.now(timezone.utc) + timedelta(minutes=45)).strftime('%Y-%m-%dT%H:%M:%S')

    def intercept(route):
        req = route.request
        if req.resource_type not in ('fetch', 'xhr') or req.headers.get('rsc') == '1': return route.continue_()
        if req.method == 'OPTIONS': return route.fulfill(status=204, headers=CORS)
        path = urlparse(req.url).path.removeprefix('/api'); value = None
        if path == '/auth/me': value = USER
        elif path == '/projects': value = {'projects': [PROJECT]}
        elif path in ('/upload', '/convert'):
            sent.append((path, form_parts(req), dict(req.headers)))
            value = {'job_id': JOB, 'status': 'queued', 'created_at': '2026-10-07T00:00:00', 'message': 'ok',
                     'project': {**PROJECT, 'created': False, 'source': 'request'}}
        elif path == f'/jobs/{JOB}/source' and req.method == 'DELETE':
            state.update(assets_available=False, deleted=True)
            value = {'job_id': JOB, 'source_deleted': False, 'source_deleted_at': None, 'assets_deleted': True}
        elif path == f'/jobs/{JOB}':
            value = {'job_id': JOB, 'type': 'main', 'kind': 'document', 'status': 'completed', 'progress': 100,
                     'name': 'deck.pdf', 'tags': [], 'created_at': '2026-10-07T00:00:00', 'completed_at': '2026-10-07T00:01:00',
                     'project': PROJECT, 'source_available': False, 'source_deleted_at': '2026-10-07T00:01:00',
                     'source_deletable': False, 'assets_available': state['assets_available'],
                     'assets_expire_at': None if state['deleted'] else expire_at}
        elif path == f'/jobs/{JOB}/result':
            value = {'job_id': JOB, 'type': 'main', 'status': 'completed', 'completed_at': '2026-10-07T00:01:00',
                     'result': {'markdown': f'# Deck\n\n![Image]({ASSETS[1]["url"]})', 'metadata': {'format': 'pdf', 'pages': 1},
                                'assets': ASSETS, 'assets_skipped': {'too_small': 2, 'count_limit': 0, 'size_limit': 0, 'unavailable': 0}}}
        elif path.startswith(f'/jobs/{JOB}/assets/'):
            assert req.headers.get('authorization') == 'Bearer synthetic-assets-token', req.headers
            if not state['assets_available']:
                return route.fulfill(status=410, json={'detail': {'code': 'SOURCE_PURGED', 'cause': 'ASSETS_PURGED'}}, headers=CORS)
            return route.fulfill(status=200, body=PNG, headers={**CORS, 'content-type': 'image/png'})
        elif path == f'/jobs/{JOB}/pages': value = {'job_id': JOB, 'total_pages': 0, 'pages_completed': 0, 'pages_failed': 0, 'pages': []}
        if value is None: return route.fulfill(status=404, json={'detail': 'Fixture unavailable'}, headers=CORS)
        route.fulfill(json=value, headers=CORS)

    page.route('**/*', intercept)
    try:
        # File tab: the image options, the retention note and the /upload fields
        page.goto(url.rstrip('/') + '/convert?project_id=' + PROJECT['id'])
        page.locator('input[type="file"]').set_input_files({'name': 'deck.pdf', 'mimeType': 'application/pdf', 'buffer': PDF})
        page.get_by_label('Extract images', exact=True).first.click()
        page.get_by_label('Render each page as an image', exact=True).first.click()
        retention = page.get_by_test_id('file-image-retention')
        expect(retention).to_contain_text('kept as long as the job')
        page.get_by_label("Don't keep the original file after converting").click()
        expect(retention).to_contain_text('1 hour by default')
        page.get_by_role('button', name='Convert to Markdown', exact=True).click()
        page.wait_for_url(f'**/jobs/{JOB}', timeout=10000)
        path, parts, _ = sent[-1]
        assert path == '/upload' and parts['image_mode'] == b'referenced' and parts['page_images'] == b'true' \
            and parts['purge_source'] == b'true' and parts['file'] == PDF, (path, parts.keys())

        # Job page: Images tab, thumbnails with the session's credentials, expiry, zip
        expect(page.get_by_role('heading', name='Converted document')).to_be_visible()
        page.get_by_role('tab', name='Images (2)').click()
        expect(page.get_by_test_id('job-images-expiry')).to_contain_text('Available until')
        expect(page.get_by_test_id('job-images')).to_contain_text('2 pictures were not saved')
        cards = page.get_by_test_id('job-asset')
        expect(cards).to_have_count(2)
        expect(cards.first.locator('img')).to_be_visible()
        assert page.evaluate("[...document.querySelectorAll('[data-testid=job-asset] img')].every(i => i.complete && i.naturalWidth > 0)")
        expect(cards.first).to_contain_text('Page 1 · full page')
        with page.expect_download() as info:
            page.get_by_role('button', name='Download all (.zip)').click()
        target = Path(info.value.path())
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None and sorted(archive.namelist()) == sorted(a['name'] for a in ASSETS)
            assert archive.read(ASSETS[0]['name']) == PNG

        # The original is already gone: the button deletes the images, and says so
        delete = page.get_by_role('button', name='Delete extracted images', exact=True)
        expect(delete).to_be_enabled(); delete.click()
        dialog = page.get_by_role('alertdialog')
        expect(dialog).to_contain_text('extracted images')
        dialog.get_by_role('button', name='Delete extracted images').click()
        expect(page.get_by_test_id('job-images-deleted')).to_be_visible()
        expect(page.get_by_role('button', name='Download all (.zip)')).to_have_count(0)

        # URL and Dropbox tabs post /convert with the image options; the provider token
        # travels in X-Source-Token, never as a form field
        page.goto(url.rstrip('/') + '/convert?project_id=' + PROJECT['id'])
        page.get_by_role('tab', name='URL').click()
        page.get_by_label('Document URL').fill('https://example.com/deck.pdf')
        page.locator('#url-extract-images').click()
        expect(page.get_by_test_id('url-image-retention')).to_contain_text('kept as long as the job')
        page.get_by_role('button', name='Convert from URL').click()
        page.wait_for_url(f'**/jobs/{JOB}', timeout=10000)
        path, parts, _ = sent[-1]
        assert path == '/convert' and parts['source_type'] == b'url' and parts['source'] == b'https://example.com/deck.pdf' \
            and parts['image_mode'] == b'referenced' and 'page_images' not in parts and 'purge_source' not in parts, parts
        page.goto(url.rstrip('/') + '/convert?project_id=' + PROJECT['id'])
        page.get_by_role('tab', name='Dropbox').click()
        page.get_by_label('Dropbox File Path').fill('/slides/deck.pdf')
        page.get_by_label('Access Token').fill('sl.provider-token')
        page.locator('#dropbox-page-images').click()
        page.get_by_role('button', name='Convert from Dropbox').click()
        page.wait_for_url(f'**/jobs/{JOB}', timeout=10000)
        path, parts, headers = sent[-1]
        assert path == '/convert' and parts['source_type'] == b'dropbox' and parts['page_images'] == b'true' \
            and 'image_mode' not in parts and 'auth_token' not in parts, parts
        assert headers.get('x-source-token') == 'sl.provider-token' and headers.get('authorization') == 'Bearer synthetic-assets-token'
        assert not errors, errors
        print(f"PASS convert image options (file/url/dropbox), Images tab, zip, expiry and delete viewport {viewport['width']}", flush=True)
    except Exception:
        print('Browser failure:', page.url, errors, page.locator('body').inner_text()[:1500], flush=True)
        raise
    finally:
        context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--url', default='http://localhost:3107'); parser.add_argument('--chromium')
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
        try:
            for viewport in ({'width': 1440, 'height': 1100}, {'width': 390, 'height': 844}): check(browser, args.url, viewport)
        finally:
            browser.close()
