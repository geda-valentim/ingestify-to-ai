#!/usr/bin/env python3
"""Real draft configuration, per-request partitions, JSONL/retry and mobile UI."""
import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from minio import Minio
from playwright.sync_api import expect, sync_playwright


def check_mobile(browser, api, auth, args, connection, errors, passed):
    config = connection["config"]
    mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    mobile.add_init_script('localStorage.setItem("auth-storage", ' + json.dumps(auth) + ');')
    phone = mobile.new_page(); phone.on('pageerror', lambda error: errors.append(str(error)))
    phone.goto(args.url + '/datalakes', wait_until='networkidle')
    phone.locator('article').filter(has=phone.get_by_role('heading', name='Partitions check', exact=True)).get_by_role('button', name='Editar', exact=True).click()
    dialog = phone.get_by_role('dialog'); dialog.get_by_role('button', name='Ver buckets', exact=True).click()
    dialog.get_by_role('button', name='Continuar', exact=True).click()
    dialog.get_by_label('Estratégia de particionamento').select_option('custom')
    dialog.get_by_role('button', name='Adicionar campo', exact=True).click()
    dialog.get_by_label('Chave do campo 2', exact=True).fill('departamento')
    dialog.get_by_label('departamento', exact=True).fill('suporte')
    dialog.get_by_label('Exportação analítica').select_option('jsonl')
    expect(dialog.get_by_label('Prévia do particionamento')).to_contain_text('/departamento=suporte/', timeout=15000)
    dialog.get_by_label('Prévia do particionamento').scroll_into_view_if_needed()
    dialog.screenshot(path=str(args.fixture.parent / 'partition-wizard-mobile.png'))
    assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    box = dialog.bounding_box(); assert box['y'] >= 0 and box['y'] + box['height'] <= 844
    dialog.get_by_role('button', name='Cancelar', exact=True).click()
    assert api.get('/datalakes').json()['connections'][0]['config'] == config
    phone.goto(args.url + '/live', wait_until='networkidle')
    fieldset = phone.locator('fieldset').filter(has=phone.locator('legend').get_by_text('Destino dos resultados', exact=True))
    fieldset.get_by_label('1. Conexão', exact=True).select_option(connection['id'])
    fieldset.get_by_label('Personalizar particionamento nesta solicitação').check()
    fieldset.get_by_label('Estratégia de particionamento').select_option('custom')
    fieldset.get_by_label('Campo 1', exact=True).select_option('source_type')
    expect(fieldset.get_by_label('Prévia do particionamento')).to_contain_text('source_type=live', timeout=15000)
    assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    passed('custom partition configuration and live destination preview fit mobile viewport')
    mobile.close()


def main(args):
    state = json.loads(args.fixture.read_text())
    assert state['user']['username'].startswith('datalake-check-')
    assert args.mobile_only or not state['connections'], 'Use a fresh isolated fixture'
    def save():
        args.fixture.write_text(json.dumps(state)); args.fixture.chmod(0o600)
    def passed(message):
        print('passed:', message, flush=True)
    api = httpx.Client(base_url=args.url + '/api', headers={'Authorization': 'Bearer ' + state['token']}, timeout=30)
    storage = Minio('localhost:9002', secure=False, **state['credentials'])
    auth = json.dumps({'state': {'user': state['user'], 'token': state['token']}, 'version': 0})
    if args.mobile_only:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=args.chromium, args=['--no-sandbox'])
            errors = []
            check_mobile(browser, api, auth, args, api.get('/datalakes').json()['connections'][0], errors, passed)
            assert not errors, errors
            browser.close()
        api.close()
        return
    spec = importlib.util.spec_from_file_location('datalake_ui_checks', Path(__file__).with_name('datalakes-browser.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.chromium, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        context.add_init_script('localStorage.setItem("auth-storage", ' + json.dumps(auth) + ');')
        page = context.new_page(); errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url + '/datalakes', wait_until='networkidle')
        page.get_by_role('button', name='Nova conexão', exact=True).click()
        dialog = page.get_by_role('dialog')
        dialog.get_by_label('Nome da conexão').fill('Partitions check')
        dialog.get_by_label('Provedor', exact=True).select_option('minio')
        dialog.locator('#datalake-endpoint').fill(state['endpoint'])
        dialog.get_by_label('Access key', exact=True).fill(state['credentials']['access_key'])
        dialog.get_by_label('Secret key', exact=True).fill(state['credentials']['secret_key'])
        dialog.get_by_role('button', name='Ver buckets', exact=True).click()
        for bucket in state['buckets']:
            dialog.get_by_label('Permitir ' + bucket, exact=True).check(timeout=15000)
        dialog.get_by_role('button', name='Continuar', exact=True).click()
        dialog.get_by_label('Bucket padrão (opcional)').select_option(state['buckets'][0])
        dialog.get_by_label('Pasta padrão (opcional)').fill('exports')
        dialog.get_by_label('Estratégia de particionamento').select_option('custom')
        dialog.get_by_role('button', name='Adicionar campo', exact=True).click()
        dialog.get_by_label('Campo 2', exact=True).select_option('custom')
        dialog.get_by_label('Chave do campo 2', exact=True).fill('cliente')
        dialog.get_by_label('cliente', exact=True).fill('equipe')
        dialog.get_by_role('button', name='Subir campo 2', exact=True).click()
        dialog.get_by_label('Granularidade da data').select_option('hour')
        dialog.get_by_label('Fuso horário').fill('America/Sao_Paulo')
        dialog.get_by_label('Quando um valor estiver ausente').select_option('require')
        dialog.get_by_label('Exportação analítica').select_option('jsonl')
        preview = dialog.get_by_label('Prévia do particionamento')
        expect(preview).to_contain_text('/cliente=equipe/year=', timeout=15000)
        expect(preview).to_contain_text('/hour=')
        expect(preview).to_contain_text('/datasets/layout-')
        dialog.get_by_label('Fuso horário').fill('Invalid/Timezone')
        expect(dialog.get_by_role('alert')).to_be_visible(timeout=15000)
        expect(dialog.get_by_role('button', name='Continuar', exact=True)).to_be_disabled()
        dialog.get_by_label('Fuso horário').fill('America/Sao_Paulo')
        dialog.get_by_role('button', name='Adicionar campo', exact=True).click()
        dialog.get_by_label('Chave do campo 3', exact=True).fill('cliente')
        expect(dialog.get_by_role('alert')).to_be_visible(timeout=15000)
        expect(dialog.get_by_role('button', name='Continuar', exact=True)).to_be_disabled()
        dialog.get_by_role('button', name='Remover campo 3', exact=True).click()
        expect(dialog.get_by_role('button', name='Continuar', exact=True)).to_be_enabled(timeout=15000)
        assert api.get('/datalakes').json()['connections'] == []
        dialog.screenshot(path=str(args.fixture.parent / 'partition-wizard-desktop.png'))
        dialog.get_by_role('button', name='Continuar', exact=True).click()
        dialog.get_by_role('button', name='Salvar conexão', exact=True).click()
        expect(dialog).not_to_be_visible(timeout=15000)
        connection = api.get('/datalakes').json()['connections'][0]
        state['connections']['minio'] = connection['id']; save()
        assert connection['config']['partitioning']['fields'][0]['key'] == 'cliente'
        passed('custom order, timezone, granularities, defaults, required values, JSONL and invalid preview blocks save')

        page.goto(args.url + '/dashboard?project=Partition%20check', wait_until='networkidle')
        destination = page.locator('fieldset').filter(has=page.locator('legend').get_by_text('Destino dos resultados', exact=True))
        destination.get_by_label('1. Conexão', exact=True).select_option(connection['id'])
        expect(destination.get_by_label('cliente (obrigatório)', exact=True)).to_have_value('equipe')
        destination.get_by_label('Personalizar particionamento nesta solicitação').check()
        destination.get_by_label('Estratégia de particionamento').select_option('project_date')
        expect(destination.get_by_label('Prévia do particionamento')).to_contain_text('project_id=novo-projeto', timeout=15000)
        expect(destination).to_contain_text('IDs ilustrativos')
        destination.get_by_role('button', name='Usar padrões da conexão', exact=True).click()
        expect(destination.get_by_label('Personalizar particionamento nesta solicitação')).not_to_be_checked()
        expect(destination.get_by_label('cliente (obrigatório)', exact=True)).to_have_value('equipe')
        destination.get_by_label('2. Bucket', exact=True).select_option(state['buckets'][1])
        destination.get_by_label('Personalizar particionamento nesta solicitação').check()
        destination.get_by_label('Granularidade da data').select_option('month')
        customer = 'acme / São=100%'
        destination.get_by_label('cliente (obrigatório)', exact=True).fill(customer)
        preview = destination.get_by_label('Prévia do particionamento')
        expect(preview).to_contain_text('cliente=' + quote(customer, safe='-_'), timeout=15000)
        assert '/day=' not in preview.inner_text()
        expected_preview = preview.inner_text()
        page.locator('input[type=file]').set_input_files({'name': 'partition-check.pdf', 'mimeType': 'application/pdf', 'buffer': module.pdf('Partition verification')})
        with page.expect_response(lambda r: r.url.endswith('/api/upload') and r.request.method == 'POST') as response:
            page.get_by_role('button', name='Processar arquivo', exact=True).click()
        assert response.value.ok, response.value.text()
        job_id = response.value.json()['job_id']; state['jobs'].append(job_id); save()
        api.patch('/datalakes/' + connection['id'], json={'enabled': False}).raise_for_status()
        first = api.get('/jobs/' + job_id + '/datalake').json()['destination']
        assert first['bucket'] == state['buckets'][1]
        assert first['partitioning']['granularity'] == 'month'
        assert first['partitions']['cliente'] == customer
        assert first['layout_id'] in expected_preview
        assert first['dataset_path'].endswith(job_id + '.jsonl')
        def wait_for_delivery(status):
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                job = api.get('/jobs/' + job_id).json()
                assert job['status'] != 'failed', job.get('error')
                result = api.get('/jobs/' + job_id + '/datalake').json()['destination']
                if result['status'] == status: return result
                time.sleep(2)
            raise AssertionError('Delivery did not reach ' + status)
        wait_for_delivery('failed')
        config = {**connection['config'], 'default_prefix': 'changed-after-submission', 'partitioning': {'mode': 'date', 'timezone': 'UTC', 'analytics': 'none'}, 'default_partition_values': {}}
        updated = api.patch('/datalakes/' + connection['id'], json={'enabled': True, 'config': config})
        updated.raise_for_status(); config = updated.json()['config']
        page.goto(args.url + '/jobs/' + job_id, wait_until='networkidle')
        page.get_by_role('button', name='Tentar entrega novamente', exact=True).click()
        delivery = wait_for_delivery('completed')
        assert delivery['resolved_path'] == first['resolved_path']
        assert delivery['dataset_path'] == first['dataset_path']
        assert len(delivery['objects']) == 5
        def read(key):
            result = storage.get_object(delivery['bucket'], key)
            try: return result.read()
            finally: result.close(); result.release_conn()
        data = read(delivery['dataset_path'])
        record = json.loads(data)
        assert record['job_id'] == job_id and 'Partition verification' in record['text']
        assert record['schema_version'] == 1
        schema = json.loads(read(delivery['schema_path']))
        assert [c['name'] for c in schema['partition_columns']] == ['cliente', 'year', 'month']
        assert all(obj.object_name.endswith('.jsonl') for obj in storage.list_objects(delivery['bucket'], prefix=schema['dataset_root'] + '/', recursive=True))
        assert delivery['schema_path'].startswith('exports/schemas/')
        expect(page.get_by_text('Resultados entregues', exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_text('Dataset JSONL:', exact=False)).to_contain_text(delivery['dataset_path'])
        passed('real PDF conversion and partitioned JSONL delivery, overrides, escaped fields, retry retains original default and layout')
        # Direct repeated worker delivery is exercised by pytest; record the real
        # artifact hash so future runs can compare the isolated export.
        state['dataset_hash'] = hashlib.sha256(data).hexdigest(); save()
        context.close()
        check_mobile(browser, api, auth, args, api.get("/datalakes").json()["connections"][0], errors, passed)
        assert not errors, errors
        browser.close()
    api.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='https://dev.ingestify.ai')
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--mobile-only', action='store_true', help='Resume mobile checks with an existing isolated fixture')
    parser.add_argument('--chromium', default='/root/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell')
    main(parser.parse_args())
