"""Replay instrumentation tests. Fake transport never qualifies inference quality."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from shared.live.diarization import DiarizationState, annotate_result

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/benchmark_live_transcribe.py'
spec = importlib.util.spec_from_file_location('live_benchmark', SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def update():
    return {'type':'diarization.update', 'generation':7, 'revision':1,
            'horizon_samples':160, 'replace_from_samples':0, 'replace_to_samples':160,
            'stable_until_samples':160, 'speakers':[{'id':'SPEAKER_00','label':'Falante 1'}],
            'turns':[{'start_samples':0,'end_samples':160,'speaker_id':'SPEAKER_00'}]}


@pytest.mark.parametrize('protocol,corruption', [(1,None),(2,None),(2,'digest'),(2,'turns'),
                                               (2,'text'),(2,'revision')])
def test_replay_negotiates_validates_and_writes_evidence(tmp_path, monkeypatch, protocol, corruption):
    import httpx
    import websockets
    monkeypatch.setenv('LIVE_API_KEY', 'private-test-api-key')
    monkeypatch.delenv('LIVE_BEARER_TOKEN', raising=False)
    audio = tmp_path / 'input.pcm'
    audio.write_bytes(b'\0\0' * 160)
    finals = [{'start':0.0,'end':.01,'text':'teste'}]
    state = DiarizationState(7)
    state.apply(update(),160)
    payload = annotate_result(state, {'segments':finals}, {}) if protocol == 2 else {'segments':finals}
    if corruption == 'turns':
        payload['diarization']['turns'][0]['end'] = .009
    if corruption == 'text':
        payload['segments'][0]['text'] = 'alterado'
    sent, posted, deleted = [], [], []

    class HTTP:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            posted.append(kwargs['json'])
            return SimpleNamespace(status_code=201, json=lambda:{'job_id':'job', 'ws_url':'ws://test', 'ticket':'private-ticket'})
        async def get(self, url, **kwargs):
            return SimpleNamespace(raise_for_status=lambda:None, json=lambda:payload)
        async def delete(self, url, **kwargs): deleted.append(url)

    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.seq = 0
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def __aiter__(self): return self
        async def __anext__(self): return await self.queue.get()
        def emit(self, event):
            self.seq += 1
            self.queue.put_nowait(json.dumps({**event,'event_seq':self.seq}))
        async def send(self, message):
            sent.append(message)
            if isinstance(message, str):
                message = json.loads(message)
                if message['type'] == 'authenticate':
                    self.emit({'type':'session.ready','protocol':protocol,'generation':7,'backend':'whisper','model':'fixture'})
                elif message['type'] == 'finish':
                    self.emit({'type':'session.completed','inference_seconds':.001,
                               'diarization_digest':'wrong' if corruption=='digest' else state.digest()})
            else:
                self.emit({'type':'transcript.final',**finals[0]})
                if protocol == 2:
                    self.emit({**update(),'revision':3 if corruption=='revision' else 1})
            await asyncio.sleep(0)

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs:HTTP())
    monkeypatch.setattr(websockets, 'connect', lambda *args, **kwargs:Socket())
    output = tmp_path / 'report.json'
    args = SimpleNamespace(audio=str(audio), api_url='http://test', project='Test', seconds=None,
                           phase='warm', output=str(output), diarize=protocol==2)
    result = asyncio.run(benchmark.replay(args))
    report = json.loads(output.read_text())
    assert posted[0]['protocol'] == protocol and posted[0]['diarize'] == (protocol==2)
    assert json.loads(sent[0])['protocol'] == protocol
    assert report['frames'][0]['end_samples'] == 160
    assert report['frames'][0]['send_started_seconds'] >= .01
    assert 'private-ticket' not in output.read_text() and 'private-test-api-key' not in output.read_text()
    assert report['release_gate'].startswith('not-approved')
    assert report['inference_measurement_scope'] == 'asr-only'
    if corruption:
        assert result == 1 and report['outcome'] == 'failed'
        assert not report.get('persisted_speakers_match_events')
    else:
        assert result == 0 and report['persisted_final_matches_events']
        if protocol == 2:
            assert report['persisted_speakers_match_events']
            assert report['speaker_state_digest'] == state.digest()
            assert report['speaker_labels_observed_before_finish']
            assert 'not rendered browser' in report['speaker_observation_reference']


def test_receiver_error_propagates_without_waiting_for_timeout():
    async def run():
        async def broken(): raise ValueError('broken stream')
        receiver = asyncio.create_task(broken())
        with pytest.raises(ValueError, match='broken stream'):
            await benchmark.wait_for_event(asyncio.Event(), receiver, 30)
    asyncio.run(run())


def test_complete_digest_cannot_hide_unfrozen_tail():
    evidence = benchmark.SpeakerEvidence()
    evidence.ready({'protocol':2,'generation':7})
    evidence.update({**update(),'stable_until_samples':0},160)
    with pytest.raises(RuntimeError, match='clock/digest'):
        evidence.completed({'diarization_digest':evidence.state.digest()},160)
