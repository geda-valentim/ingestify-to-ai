#!/usr/bin/env python3
"""Verify catalog-driven audio requests and configuration/result recovery after F5."""
import argparse
import json
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / 'docs/doc2md_openapi.json').read_text())
PARAMETERS = SCHEMA['components']['schemas']['AudioDecodingOptions']
PARAMETERS = {**PARAMETERS, '$defs': {'VadParameters': SCHEMA['components']['schemas']['VadParameters']}}
FASTER_KEYS = {'task', 'language', 'log_progress', 'beam_size', 'best_of', 'patience', 'length_penalty',
    'repetition_penalty', 'no_repeat_ngram_size', 'temperature', 'compression_ratio_threshold',
    'log_prob_threshold', 'no_speech_threshold', 'condition_on_previous_text', 'prompt_reset_on_temperature',
    'initial_prompt', 'prefix', 'suppress_blank', 'suppress_tokens', 'without_timestamps', 'max_initial_timestamp',
    'prepend_punctuations', 'append_punctuations', 'multilingual', 'vad_filter', 'vad_parameters', 'max_new_tokens',
    'chunk_length', 'clip_timestamps', 'hallucination_silence_threshold', 'hotwords', 'language_detection_threshold',
    'language_detection_segments'}
PARAMETERS['properties'] = {key: value for key, value in PARAMETERS['properties'].items() if key in FASTER_KEYS}
PARAMETERS['properties']['task']['enum'] = ['transcribe']
PARAMETERS['properties']['language']['enum'] = [None, 'en', 'pt', 'yue']
USER = {'id': 'audio-test', 'username': 'audio-test', 'email': 'audio@example.test', 'is_active': True, 'is_admin': False}
PROJECT = {'id': 'audio-project', 'name': 'Audio checks', 'archived': False, 'folders': []}
JOB = '66666666-6666-4666-8666-666666666666'
CORS = {'access-control-allow-origin': '*', 'access-control-allow-headers': '*'}


def check(browser, url, operation, source='file'):
    context = browser.new_context(viewport={'width': 1440, 'height': 1100})
    auth = json.dumps({'state': {'user': USER, 'token': 'synthetic-audio-token'}, 'version': 0})
    context.add_init_script('localStorage.setItem("auth-storage", ' + json.dumps(auth) + ');')
    page = context.new_page()
    captured, errors = [], []
    configuration = {'operation': 'transcription', 'provider': 'faster-whisper', 'model': 'turbo', 'options': {}}
    result = {'text': 'AUDIO_RESULT', 'segments': [{'start': 0, 'end': 1, 'text': 'AUDIO_RESULT'}] if operation == 'transcribe' else [],
              'language': 'pt', 'language_probability': .97, 'duration': 1, 'operation': operation,
              'media_info': {'channels': 1, 'sample_rate': 16000, 'codec': 'pcm_s16le'}}
    page.on('pageerror', lambda error: errors.append(str(error)))

    def intercept(route):
        request = route.request
        if request.resource_type not in ('fetch', 'xhr'): return route.continue_()
        if request.method == 'OPTIONS': return route.fulfill(status=204, headers=CORS)
        path = urlparse(request.url).path.removeprefix('/api')
        if path == '/auth/me': value = USER
        elif path == '/projects': value = {'projects': [PROJECT]}
        elif path == '/datalakes': value = {'connections': [{'id': 'audio-lake', 'name': 'Audio lake', 'provider': 'minio', 'enabled': True,
            'config': {'buckets': ['source-bucket'], 'default_bucket': 'source-bucket', 'default_prefix': ''}}]}
        elif path == '/datalakes/audio-lake/buckets': value = {'buckets': ['source-bucket']}
        elif path == '/datalakes/audio-lake/objects': value = {'objects': [{'key': 'recording.wav', 'size': 100}]}
        elif path == '/audio/capabilities':
            value = {'enabled': True, 'provider': 'faster-whisper', 'model': 'turbo', 'tasks': ['transcribe'],
                'operations': ['transcribe', 'detect_language', 'inspect'], 'formats': ['markdown', 'vtt', 'srt', 'txt', 'json'],
                'parameters_schema': PARAMETERS, 'restrictions': ['turbo não suporta tradução.'],
                'max_audio_size_mb': 50, 'max_video_size_mb': 500}
        elif path in ('/transcribe', '/convert', '/datalakes/import') and request.method == 'POST':
            if path == '/datalakes/import':
                body = request.post_data_json
                assert body['key'] == 'recording.wav' and body['bucket'] == 'source-bucket'
                wrapper = body['audio_options']
                assert 'conversion_options' not in body
            else:
                message = BytesParser(policy=default).parsebytes(b'Content-Type: ' + request.headers['content-type'].encode() + b'\r\n\r\n' + request.post_data_buffer)
                parts = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True) for part in message.iter_parts()}
                if path == '/convert':
                    assert parts['source_type'].decode() == source and 'conversion_options' not in parts
                    wrapper = json.loads(parts['audio_options'])
            if path != '/transcribe':
                parts = {key: json.dumps(value).encode() if isinstance(value, bool) else str(value).encode()
                    for key, value in wrapper.items() if key != 'decoding'}
                parts['decoding_options'] = json.dumps(wrapper['decoding']).encode()
            assert parts['operation'].decode() == operation
            options = json.loads(parts.get('decoding_options', b'{}'))
            if operation == 'transcribe':
                assert options == {'beam_size': 3, 'language': 'pt', 'temperature': [0, .2], 'hotwords': 'Ingestify',
                    'initial_prompt': 'technical lecture', 'vad_parameters': {'threshold': .4}}
                assert parts['include_word_timestamps'] == b'true' and parts['include_timestamps'] == b'false'
            else: assert options == {}
            assert parts['output_format'] == b'json' and parts['purge_source'] == b'true'
            captured.append(parts)
            configuration['options'] = {**options, 'operation': operation, 'output_format': 'json', 'purge_source': True}
            value = {'job_id': JOB, 'status': 'queued', 'project': PROJECT}
        elif path == '/jobs/' + JOB:
            value = {'job_id': JOB, 'type': 'main', 'kind': 'transcription', 'status': 'completed', 'progress': 100,
                'created_at': '2026-10-06T00:00:00', 'name': 'recording.wav', 'configuration': configuration}
        elif path == '/jobs/' + JOB + '/pages': value = {'pages': [], 'total_pages': 0}
        elif path == '/jobs/' + JOB + '/result':
            value = result if urlparse(request.url).query == 'format=json' else {'job_id': JOB, 'status': 'completed',
                'result': {'markdown': 'AUDIO_RESULT', 'metadata': {'format': 'wav', 'size_bytes': 100,
                    'available_formats': ['markdown', 'vtt', 'srt', 'txt', 'json'], 'language': 'pt'}}}
        else: return route.fulfill(status=404, json={'detail': 'Unavailable in fixture'}, headers=CORS)
        route.fulfill(json=value, headers=CORS)

    page.route('**/*', intercept)
    try:
        page.goto(url.rstrip('/') + '/convert?project_id=' + PROJECT['id'])
        submit_name = {'file': 'Processar arquivo', 'url': 'Convert from URL', 'gdrive': 'Convert from Google Drive',
            'dropbox': 'Convert from Dropbox', 'datalake': 'Processar arquivo do bucket'}[source]
        if source == 'file':
            page.locator('input[type="file"]').set_input_files({'name': 'recording.wav', 'mimeType': 'audio/wav', 'buffer': b'RIFF-audio'})
        else:
            page.get_by_role('tab', name={'url': 'URL', 'gdrive': 'Google Drive', 'dropbox': 'Dropbox', 'datalake': 'Datalake'}[source], exact=True).click()
            if source == 'datalake':
                origin = page.locator('fieldset').filter(has=page.get_by_text('Datalake de origem', exact=True))
                origin.get_by_label('1. Conexão', exact=True).select_option('audio-lake')
                page.get_by_label('Arquivo no bucket', exact=True).fill('recording.wav')
            else:
                page.get_by_label('Tipo de processamento').select_option('audio')
                page.get_by_label({'url': 'Document URL', 'gdrive': 'Google Drive File ID', 'dropbox': 'Dropbox File Path'}[source], exact=True).fill('https://example.test/recording.wav')
                if source in ('gdrive', 'dropbox'):
                    page.get_by_label('OAuth2 Token' if source == 'gdrive' else 'Access Token', exact=True).fill('fixture-provider-token')
        page.get_by_label('Operação de áudio').select_option(operation)
        if operation == 'transcribe':
            assert page.get_by_label('Task', exact=True).locator('option[value="translate"]').count() == 0
            page.get_by_label('Beam Size', exact=True).fill('3')
            page.get_by_label('Language', exact=True).select_option('"pt"')
            page.get_by_label('Temperature', exact=True).fill('[0,0.2]')
            page.get_by_label('Hotwords', exact=True).fill('Ingestify')
            page.get_by_label('Initial Prompt', exact=True).fill('"technical lecture"')
            page.get_by_role('button', name='Configurar Vad Parameters').click()
            page.get_by_label('Threshold', exact=True).fill('0.4')
            page.get_by_label('Timestamps de palavras', exact=True).check()
            page.get_by_label('Marcas de tempo no Markdown', exact=True).uncheck()
            page.get_by_label('Temperature', exact=True).fill('[invalid')
            expect(page.get_by_role('button', name=submit_name, exact=True)).to_be_disabled()
            page.get_by_label('Temperature', exact=True).fill('[0,0.2]')
        page.get_by_label('Formato padrão do resultado').select_option('json')
        page.get_by_label('Apagar arquivo original após concluir').check()
        page.get_by_role('button', name=submit_name, exact=True).click()
        page.wait_for_url('**/jobs/' + JOB, timeout=45000)
        expect(page.get_by_text('Configuração solicitada', exact=True)).to_be_visible()
        page.get_by_text('Parâmetros', exact=True).click()
        expect(page.get_by_text('faster-whisper', exact=False)).to_be_visible()
        if operation == 'transcribe': expect(page.get_by_text('Ingestify', exact=True)).to_be_visible()
        elif operation == 'inspect': expect(page.get_by_text('pcm_s16le', exact=False)).to_be_visible()
        else: expect(page.get_by_text('Probabilidade: 97.0%', exact=True)).to_be_visible()
        page.reload()
        expect(page.get_by_text('Configuração solicitada', exact=True)).to_be_visible()
        assert len(captured) == 1 and not errors, errors
        print('PASS: audio ' + operation + ', source=' + source + ', request options, configured result and F5', flush=True)
    finally: context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:3001')
    parser.add_argument('--chromium')
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
        try:
            for source in ('file', 'url', 'gdrive', 'dropbox', 'datalake'):
                for operation in ('transcribe', 'detect_language', 'inspect'): check(browser, args.url, operation, source)
        finally: browser.close()
