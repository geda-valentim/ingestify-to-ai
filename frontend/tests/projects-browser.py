#!/usr/bin/env python3
"""Real CRUD/move UI against a dedicated development fixture account.

Supply a private JSON fixture with user/token, two completed document jobs,
their result_hashes, source/destination projects and an empty destination folder.
The username must start with projects-check-. No API response is mocked.
  python frontend/tests/projects-browser.py --url https://dev.ingestify.ai \
    --fixture /tmp/ingestify-projects-validation/state.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import time
from urllib.parse import urlparse

import httpx
from playwright.sync_api import sync_playwright, expect


def prepare(args):
    """Create owned fixtures through real REST; checkpoint IDs before polling."""
    assert urlparse(args.url).hostname in {'dev.ingestify.ai', 'localhost', '127.0.0.1'}, 'Prepare fixtures only in development'
    assert not args.fixture.exists(), 'Existing fixture state must be resumed; omit --prepare'
    args.fixture.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.fixture.parent.chmod(0o700)
    def save(state):
        args.fixture.write_text(json.dumps(state, indent=2)); args.fixture.chmod(0o600)
    def pdf(text):
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
        stream = f'BT /F1 16 Tf 70 700 Td ({text}) Tj ET'.encode()
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
        data, offsets = b'%PDF-1.4\n', []
        for index, obj in enumerate(objects, 1):
            offsets.append(len(data)); data += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
        start = len(data)
        data += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets)
        return data + f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    with httpx.Client(base_url=args.api_url or args.url.rstrip('/') + '/api', headers={'User-Agent': 'Mozilla/5.0'}, timeout=30) as api:
        username, password = 'projects-check-' + secrets.token_hex(4), secrets.token_hex(8)
        result = api.post('/auth/register', json={'username': username, 'email': username + '@example.com', 'password': password})
        result.raise_for_status(); state = {'user': result.json(), 'projects': {}, 'jobs': [], 'result_hashes': {}}
        save(state)
        result = api.post('/auth/login', data={'username': username, 'password': password}); result.raise_for_status()
        state['token'] = result.json()['access_token']; save(state)
        api.headers['Authorization'] = 'Bearer ' + state['token']
        for name in ('Source project', 'Destination project'):
            result = api.post('/projects', json={'name': name}); result.raise_for_status()
            state['projects'][name] = result.json()['id']; save(state)
        result = api.post('/projects/' + state['projects']['Destination project'] + '/folders', json={'name': 'Audio'})
        result.raise_for_status(); state['folder_id'] = result.json()['id']; save(state)
        for name in ('Move check one', 'Move check two'):
            result = api.post('/upload', data={'name': name, 'project_id': state['projects']['Source project'], 'tags': 'project-maintenance'},
                files={'file': (name + '.pdf', pdf(name + ' ' + username), 'application/pdf')})
            result.raise_for_status(); state['jobs'].append(result.json()['job_id']); save(state)
        deadline = time.monotonic() + 180
        while True:
            statuses = []
            for job_id in state['jobs']:
                result = api.get('/jobs/' + job_id); result.raise_for_status(); statuses.append(result.json()['status'])
            assert 'failed' not in statuses, 'Fixture conversion failed; inspect the saved job handles'
            if all(status == 'completed' for status in statuses):
                break
            assert time.monotonic() < deadline, 'Fixtures remain nonterminal; resume saved jobs without resubmitting'
            time.sleep(2)
        for job_id in state['jobs']:
            result = api.get('/jobs/' + job_id + '/result'); result.raise_for_status()
            state['result_hashes'][job_id] = hashlib.sha256(result.content).hexdigest()
        save(state)


def check(args):
    state = json.loads(args.fixture.read_text())
    assert state['user']['username'].startswith('projects-check-'), 'Use a dedicated fixture account'
    source, destination = state['projects']['Source project'], state['projects']['Destination project']
    jobs = state['jobs']
    assert len(jobs) == 2 and len(state['result_hashes']) == 2
    api_url = args.api_url or args.url.rstrip('/') + '/api'
    report = {'public_url': args.url, 'checks': [], 'page_errors': []}
    def record(name):
        report['checks'].append(name)
        print('passed:', name, flush=True)

    with httpx.Client(base_url=api_url, headers={'Authorization': 'Bearer ' + state['token'], 'User-Agent': 'Mozilla/5.0'}, timeout=30) as api:
        def status(job_id):
            result = api.get('/jobs/' + job_id); result.raise_for_status(); return result.json()
        def unchanged_results():
            for job_id in jobs:
                result = api.get('/jobs/' + job_id + '/result'); result.raise_for_status()
                assert hashlib.sha256(result.content).hexdigest() == state['result_hashes'][job_id]
                assert status(job_id)['tags'] == ['project-maintenance']
        for job_id in jobs:
            assert status(job_id)['status'] == 'completed'

        auth = json.dumps({'state': {'user': state['user'], 'token': state['token']}, 'version': 0})
        init = 'localStorage.setItem("auth-storage", ' + json.dumps(auth) + ');'
        with sync_playwright() as p:
            chromium = Path('/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome')
            browser = p.chromium.launch(headless=True, executable_path=str(chromium) if chromium.exists() else None, args=['--no-sandbox'])
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            context.add_init_script(init)
            page = context.new_page()
            page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
            try:
                page.goto(args.url.rstrip('/') + '/projects', wait_until='networkidle')
                expect(page.get_by_role('heading', name='Projects', exact=True)).to_be_visible()
                page.get_by_role('button', name='New project', exact=True).click()
                dialog = page.get_by_role('dialog')
                dialog.get_by_label('Name', exact=True).fill('Maintenance test')
                dialog.get_by_role('button', name='Save', exact=True).click()
                expect(dialog).not_to_be_visible()
                page.get_by_role('button', name='Edit project', exact=True).click()
                dialog.get_by_label('Name', exact=True).fill('MAINTENANCE TEST')
                dialog.get_by_label('Description').fill('Maintenance checks')
                dialog.get_by_role('button', name='Save', exact=True).click()
                expect(dialog).not_to_be_visible()
                expect(page.get_by_text('Maintenance checks', exact=True)).to_be_visible()
                page.get_by_role('button', name='Archive', exact=True).click()
                expect(page.get_by_role('button', name='Restore', exact=True)).to_be_visible()
                expect(page.get_by_role('button', name='New folder', exact=True)).to_be_disabled()
                page.get_by_role('button', name='Restore', exact=True).click()
                expect(page.get_by_role('button', name='New folder', exact=True)).to_be_enabled()
                record('create_edit_archive_restore_project')

                page.get_by_role('button', name='New folder', exact=True).click()
                dialog.get_by_label('Name', exact=True).fill('Notes')
                dialog.get_by_role('button', name='Save', exact=True).click()
                expect(dialog).not_to_be_visible()
                page.get_by_role('button', name='Edit folder Notes', exact=True).click()
                dialog.get_by_label('Name', exact=True).fill('NOTES')
                dialog.get_by_role('button', name='Save', exact=True).click()
                expect(dialog).not_to_be_visible()
                page.get_by_role('button', name='Delete folder NOTES', exact=True).click()
                page.get_by_role('alertdialog').get_by_role('button', name='Delete', exact=True).click()
                expect(page.get_by_role('alertdialog')).not_to_be_visible()
                page.get_by_role('button', name='Delete project', exact=True).click()
                page.get_by_role('alertdialog').get_by_role('button', name='Delete', exact=True).click()
                expect(page.get_by_role('alertdialog')).not_to_be_visible()
                record('create_rename_delete_folder_and_empty_project')

                page.goto(args.url.rstrip('/') + '/jobs?project_id=' + source, wait_until='networkidle')
                page.get_by_role('checkbox', name='Select all jobs on this page').check()
                expect(page.get_by_text('2 selected', exact=True)).to_be_visible()
                page.get_by_role('button', name='Move selected', exact=True).click()
                dialog = page.get_by_role('dialog')
                dialog.get_by_label('Destination project').select_option(destination)
                dialog.get_by_label('Destination folder').select_option(state['folder_id'])
                dialog.get_by_role('button', name='Move', exact=True).click()
                expect(dialog).not_to_be_visible()
                for job_id in jobs:
                    loc = status(job_id)
                    assert loc['project']['id'] == destination and loc['folder']['id'] == state['folder_id']
                unchanged_results(); record('bulk_move_preserves_results_and_tags')

                page.goto(args.url.rstrip('/') + '/jobs/' + jobs[0], wait_until='networkidle')
                page.get_by_role('button', name='Move', exact=True).click()
                dialog.get_by_label('Destination project').select_option(destination)
                dialog.get_by_label('Destination folder').select_option(state['folder_id'])
                dialog.get_by_label('Destination project').select_option(source)
                expect(dialog.get_by_label('Destination folder')).to_have_value('')
                dialog.get_by_role('button', name='Move', exact=True).click()
                expect(dialog).not_to_be_visible()
                loc = status(jobs[0]); assert loc['project']['id'] == source and loc['folder'] is None
                unchanged_results(); record('single_move_and_folder_reset')

                page.goto(args.url.rstrip('/') + '/projects?project_id=' + destination, wait_until='networkidle')
                page.get_by_role('button', name='Delete folder Audio', exact=True).click()
                page.get_by_role('alertdialog').get_by_role('button', name='Delete', exact=True).click()
                expect(page.get_by_role('alertdialog')).not_to_be_visible()
                loc = status(jobs[1]); assert loc['project']['id'] == destination and loc['folder'] is None
                unchanged_results(); record('folder_delete_returns_jobs_to_root')
                page.get_by_role('button', name='Delete project', exact=True).click()
                alert = page.get_by_role('alertdialog')
                alert.get_by_role('button', name='Delete', exact=True).click()
                expect(alert.get_by_role('alert')).to_contain_text('Projeto contém jobs')
                alert.get_by_role('button', name='Cancel', exact=True).click()
                record('nonempty_project_delete_is_blocked')
                summaries = api.get('/projects?include=folders'); summaries.raise_for_status()
                values = {v['id']: v for v in summaries.json()['projects']}
                for project_id in (source, destination):
                    assert values[project_id]['job_count'] == 1 and values[project_id]['completed_count'] == 1
                    assert values[project_id]['root_job_count'] == 1 and values[project_id]['total_bytes'] > 0
                expect(page.get_by_role('region', name='Project statistics')).to_be_visible()
                page.screenshot(path=str(args.fixture.parent / 'projects-desktop.png'), full_page=True)
                record('statistics_reflect_moves')

                mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                mobile.add_init_script(init)
                phone = mobile.new_page(); phone.on('pageerror', lambda error: report['page_errors'].append(str(error)))
                phone.goto(args.url.rstrip('/') + '/projects?project_id=' + source, wait_until='networkidle')
                expect(phone.get_by_role('heading', name='Statistics', exact=True)).to_be_visible()
                assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                phone.screenshot(path=str(args.fixture.parent / 'projects-mobile.png'), full_page=True)
                mobile.close(); record('mobile_layout_without_horizontal_overflow')
                assert not report['page_errors']
                report['outcome'] = 'passed'
            finally:
                output = args.fixture.parent / 'browser-report.json'
                output.write_text(json.dumps(report, indent=2) + '\n'); output.chmod(0o600)
                browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://dev.ingestify.ai')
    parser.add_argument('--api-url')
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true', help='Create a dedicated development account and PDF fixtures first')
    args = parser.parse_args()
    if args.prepare:
        prepare(args)
    check(args)
