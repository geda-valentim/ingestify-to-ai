"""Catalog-driven live capture; synthetic microphone/socket, no model or real account."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

USER = {'id': 'live-test', 'username': 'live-test', 'email': 'live@example.test', 'is_admin': False}
JOB = '77777777-7777-4777-8777-777777777777'


def check(browser, url, width):
    schemas = json.loads((Path(__file__).resolve().parents[1] / 'docs/doc2md_openapi.json').read_text())['components']['schemas']
    schema = {**schemas['LiveOptions'], '$defs': schemas}
    context = browser.new_context(viewport={'width': width, 'height': 1000}, permissions=['microphone'])
    context.add_init_script('localStorage.setItem("auth-storage", '+json.dumps(json.dumps({'state': {'user': USER, 'token': 'synthetic-live-token'}, 'version': 0}))+');')
    page = context.new_page()
    captured, errors = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    configuration = {'operation': 'live_transcribe', 'provider': 'faster-whisper', 'model': 'turbo', 'options': {}}
    ready = True
    def intercept(route):
        nonlocal ready
        req = route.request
        if req.resource_type not in ('fetch', 'xhr'): return route.continue_()
        path = urlparse(req.url).path.removeprefix('/api')
        if path == '/auth/me': value = USER
        elif path == '/projects': value = {'projects': []}
        elif path == '/datalakes': value = {'connections': []}
        elif path == '/transcribe/live/sessions/capabilities':
            value = {'enabled': True, 'ready': ready, 'options_supported': True, 'languages': ['pt', 'en', 'es'],
                     'provider': 'faster-whisper', 'model': 'turbo', 'protocol': 1, 'max_duration_seconds': 60,
                     'options_schema': schema, 'managed_parameters': {}, 'restrictions': []}
        elif path == '/transcribe/live/sessions' and req.method == 'POST':
            body = req.post_data_json; captured.append(body)
            assert body['language'] == 'en'
            assert body['options']['decoding'] == {'beam_size': 3, 'initial_prompt': 'Ingestify terminology', 'hotwords': 'Data Lake', 'temperature': [0, .2]}
            assert body['options']['interval_seconds'] == 1
            configuration['options'] = {'language': body['language'], 'options': body['options']}
            value = {'job_id': JOB, 'ws_url': url.replace('http', 'ws')+'/test-live', 'ticket': 'synthetic-ticket', 'max_duration_seconds': 60}
        elif path == '/jobs/'+JOB:
            value = {'job_id': JOB, 'type': 'main', 'kind': 'transcription', 'status': 'completed', 'progress': 100,
                     'created_at': '2026-10-06T00:00:00Z', 'name': 'Live check', 'configuration': configuration}
        elif path == '/jobs/'+JOB+'/pages': value = {'pages': [], 'total_pages': 0}
        elif path == '/jobs/'+JOB+'/result':
            value = {'text': 'LIVE_RESULT', 'segments': [{'start': 0, 'end': 1, 'text': 'LIVE_RESULT'}], 'language': 'en', 'duration': 1} if urlparse(req.url).query == 'format=json' else {'job_id': JOB, 'status': 'completed', 'result': {'markdown': 'LIVE_RESULT', 'metadata': {'format': 'pcm', 'size_bytes': 32000, 'language': 'en', 'input_mode': 'live', 'available_formats': ['markdown', 'json', 'vtt', 'srt', 'txt']}}}
        else: return route.fulfill(status=404, json={'detail': 'Fixture route unavailable'})
        route.fulfill(json=value)
    page.route('**/*', intercept)
    def socket(ws):
        def receive(message):
            if not isinstance(message, str): return
            value = json.loads(message)
            if value['type'] == 'authenticate': ws.send(json.dumps({'type': 'session.ready', 'event_seq': 1}))
            elif value['type'] == 'finish':
                ws.send(json.dumps({'type': 'transcript.final', 'event_seq': 2, 'segment_id': 0, 'start': 0, 'end': 1, 'text': 'LIVE_RESULT'}))
                ws.send(json.dumps({'type': 'session.completed', 'event_seq': 3}))
        ws.on_message(receive)
    page.route_web_socket('**/test-live', socket)
    try:
        page.goto(url+'/live')
        page.locator('#uploadProject').fill('Live checks')
        page.locator('#uploadProject').press('Tab')
        page.get_by_label('Idioma da conversa').select_option('en')
        page.get_by_role('button', name='Controles do modelo · turbo', exact=True).click()
        page.get_by_role('button', name='Configurar decoding', exact=True).click()
        page.get_by_label('Beam Size', exact=True).fill('3')
        page.get_by_label('Initial Prompt', exact=True).fill('Ingestify terminology')
        page.get_by_label('Hotwords', exact=True).fill('Data Lake')
        page.get_by_label('Interval Seconds', exact=True).fill('1')
        page.get_by_label('Temperature', exact=True).fill('[bad')
        expect(page.get_by_role('button', name='Iniciar microfone')).to_be_disabled()
        page.get_by_label('Temperature', exact=True).fill('[0,0.2]')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.get_by_role('button', name='Iniciar microfone').click()
        expect(page.get_by_role('button', name='Finalizar', exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_label('Idioma da conversa')).to_be_disabled()
        page.get_by_role('button', name='Finalizar', exact=True).click()
        page.get_by_role('link', name='Ver resultado e baixar legendas').click()
        expect(page.get_by_text('Configuração solicitada', exact=True)).to_be_visible()
        page.reload()
        expect(page.get_by_text('Configuração solicitada', exact=True)).to_be_visible()
        assert len(captured) == 1 and not errors, errors
        ready = False
        page.goto(url+'/live')
        expect(page.get_by_role('button', name='Iniciar microfone')).to_be_disabled()
        expect(page.get_by_text('O worker ao vivo está indisponível.', exact=False)).to_be_visible()
        print(f'PASS: live {width}px, catalog controls, invalid JSON, capture request, socket completion, F5 and unavailable worker', flush=True)
    finally: context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--url', default='http://127.0.0.1:3114'); parser.add_argument('--chromium', default='/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome')
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])
        try:
            for width in (1440, 390): check(browser, args.url.rstrip('/'), width)
        finally: browser.close()
