#!/usr/bin/env python3
"""Real development UI/API/MinIO checks with an isolated datalake-check- user.

Pass a private fixture JSON containing user/token, two owned test buckets,
MinIO endpoint/credentials, jobs and connections. No API responses are mocked.
GCP/Azure forms use test credentials; cloud SDK contracts are checked in pytest.
"""
import argparse
import hashlib
import io
import json
import time
from pathlib import Path

import httpx
from minio import Minio
from playwright.sync_api import sync_playwright, expect


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


def main(args):
    state = json.loads(args.fixture.read_text())
    assert state['user']['username'].startswith('datalake-check-')
    assert all(b.startswith('datalake-check-') for b in state['buckets'])
    def save():
        args.fixture.write_text(json.dumps(state)); args.fixture.chmod(0o600)
    def passed(name):
        print('passed:', name, flush=True)
    storage = Minio(args.minio, secure=False, **state['credentials'])
    contents = pdf('Datalake verification ' + state['user']['username'])
    storage.put_object(state['buckets'][0], 'inputs/check.pdf', io.BytesIO(contents), len(contents), content_type='application/pdf')
    auth = json.dumps({'state': {'user': state['user'], 'token': state['token']}, 'version': 0})
    api = httpx.Client(base_url=args.url.rstrip('/') + '/api', headers={'Authorization': 'Bearer ' + state['token'], 'User-Agent': 'Mozilla/5.0'}, timeout=45)
    def complete(job_id, delivery):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            response = api.get('/jobs/' + job_id); response.raise_for_status()
            assert response.json()['status'] != 'failed', response.json().get('error')
            response = api.get(f'/jobs/{job_id}/datalake'); response.raise_for_status()
            if response.json()['destination']['status'] == delivery:
                return response.json()['destination']
            time.sleep(2)
        raise AssertionError('Job/delivery did not reach ' + delivery)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.chromium, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        context.add_init_script('localStorage.setItem("auth-storage", ' + json.dumps(auth) + ');')
        page = context.new_page(); errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url + '/datalakes', wait_until='networkidle')
        expect(page.get_by_role('heading', name='Datalakes', exact=True)).to_be_visible()
        for provider in ('s3', 'minio', 'gcs', 'azure'):
            if provider in state['connections']:
                continue  # Resume the same isolated fixture after an interrupted check.
            page.get_by_role('button', name='Nova conexão', exact=True).click()
            dialog = page.get_by_role('dialog')
            dialog.get_by_label('Nome da conexão').fill(provider + ' check')
            dialog.get_by_label('Provedor', exact=True).select_option(provider)
            if provider in ('s3', 'minio'):
                dialog.locator('#datalake-endpoint').fill(state['endpoint'])
                dialog.get_by_label('Access key', exact=True).fill(state['credentials']['access_key'])
                dialog.get_by_label('Secret key', exact=True).fill(state['credentials']['secret_key'])
            elif provider == 'gcs':
                dialog.get_by_label('JSON da conta de serviço').fill(json.dumps({'client_email': 'test@example.test', 'private_key': 'test-private-key', 'token_uri': 'https://oauth2.googleapis.com/token'}))
            else:
                dialog.get_by_label('Connection string', exact=True).fill('fixture-no-cloud-account')
            dialog.get_by_role('button', name='Ver buckets', exact=True).click()
            expect(dialog.get_by_role('heading', name='2. Buckets', exact=True)).to_be_visible()
            if provider in ('s3', 'minio'):
                for bucket_name in state['buckets']:
                    dialog.get_by_label('Permitir ' + bucket_name, exact=True).check(timeout=15000)
            else:
                expect(dialog.get_by_role('alert')).to_be_visible(timeout=15000)
                dialog.get_by_label('Permitir todos os buckets acessíveis', exact=False).check()
            assert len(api.get('/datalakes').json()['connections']) == len(state['connections']), 'Draft discovery saved a connection'
            dialog.get_by_role('button', name='Continuar', exact=True).click()
            if provider in ('s3', 'minio'):
                dialog.get_by_label('Bucket padrão (opcional)').select_option(state['buckets'][0])
            dialog.get_by_label('Pasta padrão (opcional)').fill('exports')
            dialog.get_by_role('button', name='Continuar', exact=True).click()
            expect(dialog.get_by_role('heading', name='4. Revisão', exact=True)).to_be_visible()
            dialog.get_by_role('button', name='Salvar conexão', exact=True).click()
            expect(dialog).not_to_be_visible(timeout=15000)
            connections = api.get('/datalakes').json()['connections']
            state['connections'][provider] = next(c['id'] for c in connections if c['provider'] == provider); save()
            assert all('credentials' not in c for c in connections)
            passed('frontend create ' + provider)
        current_name = next(c['name'] for c in api.get('/datalakes').json()['connections'] if c['id'] == state['connections']['minio'])
        card = page.locator('article').filter(has=page.get_by_role('heading', name=current_name, exact=True))
        card.get_by_role('button', name='Editar', exact=True).click()
        dialog = page.get_by_role('dialog')
        expect(dialog.get_by_label('Secret key', exact=True)).to_have_value('')
        dialog.get_by_label('Nome da conexão').fill('minio edited')
        dialog.get_by_role('button', name='Ver buckets', exact=True).click()
        expect(dialog.get_by_label('Permitir ' + state['buckets'][0], exact=True)).to_be_checked(timeout=15000)
        dialog.get_by_role('button', name='Continuar', exact=True).click()
        expect(dialog.get_by_label('Bucket padrão (opcional)')).to_have_value(state['buckets'][0])
        dialog.get_by_role('button', name='Continuar', exact=True).click()
        dialog.get_by_role('button', name='Salvar conexão', exact=True).click()
        expect(dialog).not_to_be_visible()
        page.locator('article').filter(has=page.get_by_role('heading', name='minio edited', exact=True)).get_by_role('button', name='Testar conexão').click()
        expect(page.get_by_text('Conexão validada.', exact=False)).to_be_visible(timeout=15000)
        passed('edit preserves encrypted credentials and real MinIO access')

        # Existing connections can be explored without saving any changes.
        before = api.get('/datalakes').json()
        page.locator('article').filter(has=page.get_by_role('heading', name='minio edited', exact=True)).get_by_role('button', name='Editar', exact=True).click()
        dialog = page.get_by_role('dialog')
        dialog.get_by_role('button', name='Ver buckets', exact=True).click()
        expect(dialog.get_by_role('button', name='Continuar', exact=True)).to_be_enabled(timeout=15000)
        dialog.get_by_label('Verificar outro bucket', exact=True).fill(state['buckets'][1])
        dialog.get_by_role('button', name='Verificar', exact=True).click()
        expect(dialog.get_by_label('Verificar outro bucket', exact=True)).to_have_value('', timeout=15000)
        dialog.get_by_role('button', name='Continuar', exact=True).click()
        dialog.get_by_label('Bucket padrão (opcional)').select_option(state['buckets'][1])
        dialog.get_by_role('button', name='Voltar', exact=True).click()
        dialog.get_by_label('Permitir ' + state['buckets'][1], exact=True).uncheck()
        dialog.get_by_role('button', name='Continuar', exact=True).click()
        expect(dialog.get_by_label('Bucket padrão (opcional)')).to_have_value('')
        dialog.get_by_role('button', name='Cancelar', exact=True).click()
        expect(dialog).not_to_be_visible()
        assert api.get('/datalakes').json() == before, 'Cancel changed the saved connection'
        passed('manual bucket verification, default constrained to selection, cancel leaves connection unchanged')

        def create_bucket_in_wizard(target, provider, suffix, use_default=True):
            current = next(c for c in api.get('/datalakes').json()['connections'] if c['id'] == state['connections'][provider])
            target.locator('article').filter(has=target.get_by_role('heading', name=current['name'], exact=True)).get_by_role('button', name='Editar', exact=True).click()
            editor = target.get_by_role('dialog')
            editor.get_by_role('button', name='Ver buckets', exact=True).click()
            expect(editor.get_by_role('button', name='Continuar', exact=True)).to_be_enabled(timeout=15000)
            editor.get_by_role('button', name='Criar bucket agora', exact=True).click()
            editor.get_by_label('Nome do novo bucket', exact=True).fill(state['buckets'][0])
            editor.get_by_role('button', name='Criar bucket', exact=True).click()
            expect(editor.get_by_role('alert')).to_contain_text('já existe', timeout=15000)
            bucket_name = state['user']['username'] + '-' + provider + '-' + suffix
            # Record before sending, so cleanup also covers uncertain responses.
            state.setdefault('created_buckets', []).append(bucket_name); save()
            editor.get_by_label('Nome do novo bucket', exact=True).fill(bucket_name)
            editor.get_by_label('Usar como bucket padrão', exact=True).set_checked(use_default)
            editor.screenshot(path=str(args.fixture.parent / ('create-bucket-' + suffix + '.png')))
            held = []
            target.route('**/api/datalakes/buckets', lambda route: held.append(route))
            editor.get_by_role('button', name='Criar bucket', exact=True).click()
            expect(editor.get_by_role('button', name='Cancelar', exact=True)).to_be_disabled()
            with target.expect_response(lambda response: response.url.endswith('/api/datalakes/buckets') and response.request.method == 'POST') as response:
                for route in held: route.continue_()
            target.unroute('**/api/datalakes/buckets')
            assert response.value.status == 201, response.value.text()
            expect(editor.get_by_label('Permitir ' + bucket_name, exact=True)).to_be_checked()
            assert storage.bucket_exists(bucket_name)
            editor.get_by_role('button', name='Continuar', exact=True).click()
            expect(editor.get_by_label('Bucket padrão (opcional)')).to_have_value(bucket_name if use_default else current['config']['default_bucket'])
            editor.get_by_role('button', name='Continuar', exact=True).click()
            expect(editor.get_by_role('status')).to_contain_text(bucket_name)
            editor.get_by_role('button', name='Cancelar', exact=True).click()
            expect(editor).not_to_be_visible()
            assert storage.bucket_exists(bucket_name), 'Cancel removed the created bucket'
            assert api.get('/datalakes').json() == before, 'Creation/cancel altered saved connection'
            passed('real ' + provider + ' bucket creation, duplicate rejection, default selection and cancel: ' + suffix)

        for provider in ('s3', 'minio'):
            create_bucket_in_wizard(page, provider, 'desktop')

        if args.settings_only:
            # Hold discovery in the browser to verify that cancellation works
            # while a provider is slow. No API response is fabricated.
            held = []
            page.route('**/api/datalakes/discover', lambda route: held.append(route))
            page.locator('article').filter(has=page.get_by_role('heading', name='minio edited', exact=True)).get_by_role('button', name='Editar', exact=True).click()
            page.get_by_role('dialog').get_by_role('button', name='Ver buckets', exact=True).click()
            expect(page.get_by_text('Consultando os buckets da conta…', exact=True)).to_be_visible()
            page.get_by_role('dialog').get_by_role('button', name='Cancelar', exact=True).click()
            expect(page.get_by_role('dialog')).not_to_be_visible()
            for route in held: route.abort()
            page.unroute('**/api/datalakes/discover')
            assert api.get('/datalakes').json() == before
            passed('cancel during bucket discovery does not save a draft')
            context.close()
            mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
            mobile.add_init_script('localStorage.setItem("auth-storage", ' + json.dumps(auth) + ');')
            phone = mobile.new_page()
            phone.goto(args.url + '/datalakes', wait_until='networkidle')
            create_bucket_in_wizard(phone, 'minio', 'mobile', use_default=False)
            phone.locator('article').filter(has=phone.get_by_role('heading', name='minio edited', exact=True)).get_by_role('button', name='Editar', exact=True).click()
            dialog = phone.get_by_role('dialog')
            dialog.get_by_role('button', name='Ver buckets', exact=True).click()
            expect(dialog.get_by_role('button', name='Continuar', exact=True)).to_be_enabled(timeout=15000)
            dialog.screenshot(path=str(args.fixture.parent / 'wizard-buckets-mobile.png'))
            dialog.get_by_role('button', name='Continuar', exact=True).click()
            expect(dialog.get_by_label('Bucket padrão (opcional)')).to_have_value(state['buckets'][0])
            dialog.get_by_role('button', name='Continuar', exact=True).click()
            expect(dialog.get_by_role('heading', name='4. Revisão', exact=True)).to_be_visible()
            assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            box = dialog.bounding_box()
            assert box['y'] >= 0 and box['y'] + box['height'] <= 844
            dialog.get_by_role('button', name='Cancelar', exact=True).click()
            assert api.get('/datalakes').json() == before
            passed('four wizard steps fit mobile viewport and preserve saved settings')
            assert not errors, errors
            browser.close(); api.close()
            return

        def dashboard():
            page.goto(args.url + '/dashboard?project=Datalake%20check', wait_until='networkidle')
            destination = page.locator('fieldset').filter(has=page.locator('legend').get_by_text('Destino dos resultados', exact=True))
            destination.get_by_label('1. Conexão', exact=True).select_option(state['connections']['minio'])
            destination.get_by_label('2. Bucket', exact=True).select_option(state['buckets'][1])
            destination.get_by_label('3. Pasta de destino (opcional)').fill('temporary')
            destination.get_by_role('button', name='Usar padrões da conexão', exact=True).click()
            expect(destination.get_by_label('2. Bucket', exact=True)).to_have_value(state['buckets'][0])
            expect(destination.get_by_label('3. Pasta de destino (opcional)')).to_have_value('exports')
            destination.get_by_label('2. Bucket', exact=True).select_option(state['buckets'][1])
            return destination
        dashboard()
        page.locator('input[type=file]').set_input_files({'name': 'check.pdf', 'mimeType': 'application/pdf', 'buffer': contents})
        with page.expect_response(lambda response: response.url.endswith('/api/upload') and response.request.method == 'POST') as response:
            page.get_by_role('button', name='Processar arquivo', exact=True).click()
        assert response.value.ok, response.value.text()
        job = response.value.json()['job_id']; state['jobs'].append(job); save()
        dest = complete(job, 'completed')
        assert dest['bucket'] == state['buckets'][1]
        assert len(dest['objects']) == 3
        for key in dest['objects']:
            assert storage.stat_object(state['buckets'][1], key).size > 0
        assert not list(storage.list_objects(state['buckets'][0], prefix='exports/', recursive=True))
        page.goto(args.url + '/jobs/' + job, wait_until='networkidle')
        expect(page.get_by_text('Resultados entregues', exact=True)).to_be_visible()
        passed('real conversion and delivery to per-request bucket, different from default')

        dashboard()
        page.get_by_role('tab', name='Datalake', exact=True).click()
        source = page.locator('fieldset').filter(has=page.locator('legend').get_by_text('Datalake de origem', exact=True))
        source.get_by_label('1. Conexão', exact=True).select_option(state['connections']['s3'])
        source.get_by_label('3. Filtrar por pasta').fill('inputs')
        page.get_by_label('Arquivo no bucket', exact=True).fill('inputs/check.pdf')
        with page.expect_response(lambda response: response.url.endswith('/api/datalakes/import') and response.request.method == 'POST') as response:
            page.get_by_role('button', name='Processar arquivo do bucket', exact=True).click()
        assert response.value.ok, response.value.text()
        job = response.value.json()['job_id']; state['jobs'].append(job); save()
        api.patch('/datalakes/' + state['connections']['minio'], json={'enabled': False}).raise_for_status()
        complete(job, 'failed')
        result_before = api.get(f'/jobs/{job}/result?format=markdown'); result_before.raise_for_status()
        result_hash = hashlib.sha256(result_before.content).hexdigest()
        api.patch('/datalakes/' + state['connections']['minio'], json={'enabled': True}).raise_for_status()
        page.goto(args.url + '/jobs/' + job, wait_until='networkidle')
        page.get_by_role('button', name='Tentar entrega novamente', exact=True).click()
        complete(job, 'completed')
        result_after = api.get(f'/jobs/{job}/result?format=markdown'); result_after.raise_for_status()
        assert hashlib.sha256(result_after.content).hexdigest() == result_hash
        expect(page.get_by_text('Resultados entregues', exact=True)).to_be_visible(timeout=15000)
        passed('bucket source via S3, failure isolation, real delivery retry preserves result')
        context.close()
        mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        mobile.add_init_script('localStorage.setItem("auth-storage", ' + json.dumps(auth) + ');')
        phone = mobile.new_page()
        phone.goto(args.url + '/datalakes', wait_until='networkidle')
        expect(phone.get_by_role('heading', name='Datalakes', exact=True)).to_be_visible()
        phone.get_by_role('button', name='Nova conexão', exact=True).click()
        phone.get_by_label('Provedor', exact=True).select_option('azure')
        expect(phone.get_by_label('Connection string', exact=True)).to_be_visible()
        phone.get_by_role('button', name='Cancelar', exact=True).click()
        phone.goto(args.url + '/dashboard?project=Datalake%20check', wait_until='networkidle')
        assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        phone.goto(args.url + '/jobs/' + job, wait_until='networkidle')
        expect(phone.get_by_text('Resultados entregues', exact=True)).to_be_visible()
        passed('mobile settings, dashboard and delivery status')
        assert not errors, errors
        browser.close()
    api.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='https://dev.ingestify.ai')
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--settings-only', action='store_true', help='Verify configuration without submitting more conversion jobs')
    parser.add_argument('--minio', default='localhost:9002')
    parser.add_argument('--chromium', default='/root/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell')
    main(parser.parse_args())
