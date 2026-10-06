"""Causal interval protocol, bounded startup/backlog and v2 admission guards."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import pytest
from shared.live.diarization import DiarizationState, annotate_result, canonical_turns
from shared.live.protocol import LiveError
from workers.live.diarizer import DiarizationBuffer, run_diarization
from tests.test_live_transcription import world

CATALOG = [{'id': 'SPEAKER_00', 'label': 'Falante 1'}, {'id': 'SPEAKER_01', 'label': 'Falante 2'}]
def turn(a, b, speaker=0):
    return {'start_samples': a, 'end_samples': b, 'speaker_id': f'SPEAKER_{speaker:02d}'}
def event(revision=1, horizon=80000, lo=0, hi=None, stable=0, turns=None):
    return {'type': 'diarization.update', 'generation': 7, 'revision': revision,
            'horizon_samples': horizon, 'replace_from_samples': lo, 'replace_to_samples': horizon if hi is None else hi,
            'stable_until_samples': stable, 'speakers': CATALOG, 'turns': turns or []}


def test_interval_replacement_clips_borders_preserves_overlap_and_unknown():
    state = DiarizationState(7)
    state.apply(event(turns=[turn(0, 80000), turn(16000, 64000, 1)]), 80000)
    state.apply(event(2, lo=32000, hi=48000, stable=32000), 100000)
    assert canonical_turns(state.turns) == [turn(0,32000), turn(16000,32000,1),turn(48000,64000,1),turn(48000,80000)]
    before = copy.deepcopy(state.frozen)
    state.apply(event(3, horizon=96000, lo=48000, stable=48000, turns=[turn(48000,96000,1)]), 120000)
    assert state.frozen[:len(before)] == before
    with pytest.raises(LiveError):
        state.apply(event(4,horizon=96000,lo=32000,stable=48000),120000)


def test_replay_gap_divergence_generation_and_late_transport():
    state = DiarizationState(7)
    first = event(stable=16000, turns=[turn(0,80000)])
    assert state.apply(first,160000)  # Arrival's PCM clock may be beyond H+5s.
    assert not state.apply(first,160000)
    second = event(2,horizon=88000,lo=16000,stable=16000)
    assert state.apply(second,160000)
    assert not state.apply(first,160000)
    for bad in ({**first, 'turns': []}, event(4), {**event(3), 'generation': 8}):
        with pytest.raises(LiveError): state.apply(bad,160000)


@pytest.mark.parametrize('field,value', [('generation',True),('revision',1.0),('horizon_samples',float('nan')),
    ('replace_from_samples',False),('stable_until_samples',80001)])
def test_samples_are_strict_integers_and_watermark_bounded(field,value):
    with pytest.raises(LiveError): DiarizationState(7).apply({**event(),field:value},80000)


def test_catalog_append_only_references_and_turn_limits():
    state = DiarizationState(7)
    for bad in ({**event(),'speakers':[CATALOG[1]]}, event(turns=[turn(0,1,2)]), event(turns=[turn(0,1)]*65)):
        with pytest.raises(LiveError): state.apply(bad,80000)
    state.apply(event(),80000)
    with pytest.raises(LiveError): state.apply({**event(2),'speakers':[]},80000)


def test_final_digest_and_exact_result_preserve_confirmed_text():
    state = DiarizationState(7)
    state.apply(event(turns=[turn(0,16000),turn(16000,48000,1),turn(40000,48000)],stable=80000),80000)
    proof={'generation':7,'revision':1,'samples':80000,'turn_count':3,'digest':state.digest()}
    state.finish(proof,80000)
    with pytest.raises(LiveError): state.finish({**proof,'digest':'0'*64},80000)
    result={'segments':[{'start':0,'end':1,'text':'a'},{'start':1,'end':3,'text':'b'}, {'start':3,'end':4,'text':'unknown'}]}
    annotated=annotate_result(state,result,{'engine':'diart'})
    assert [s['speaker_id'] for s in annotated['segments']]==['SPEAKER_00',None,None]
    assert [{k:s[k] for k in ('start','end','text')} for s in annotated['segments']]==result['segments']
    assert annotated['diarization']['turns']==[{'start':0,'end':1,'speaker_id':'SPEAKER_00'},
        {'start':1,'end':3,'speaker_id':'SPEAKER_01'},{'start':2.5,'end':3,'speaker_id':'SPEAKER_00'}]


def test_context_is_not_backlog_but_eligible_work_is():
    buffer=DiarizationBuffer()
    for _ in range(24): buffer.push(b'\0\0'*3200)
    assert buffer.incorporated==76800 and not buffer.pending and buffer.horizon==0
    buffer.push(b'\0\0'*3200)
    assert len(buffer.pending)==1
    pcm,offset,horizon=buffer.window(buffer.pending[0])
    assert len(pcm)==160000 and offset==0 and horizon==80000
    buffer.complete(80000,80000)
    for _ in range(7): buffer.push(b'\0\0'*3200)
    assert len(buffer.pending)==2
    with pytest.raises(LiveError, match='BACKPRESSURE'):
        buffer.push(b'\0\0'*9600)


def test_initial_output_deadline_and_short_eof():
    buffer=DiarizationBuffer()
    buffer.push(b'\0\0'*80000)
    with pytest.raises(LiveError,match='TIMEOUT'): buffer.push(b'\0\0'*16000)
    short=DiarizationBuffer();short.push(b'\0\0'*1234);short.finish()
    assert short.pending==[(80000,True)]
    pcm,offset,horizon=short.window(short.pending[0])
    assert len(pcm)==160000 and horizon==1234 and offset==0
    short.complete(80000,1234)
    assert not short.pending


def test_silence_and_tail_drain_freeze_real_samples_only():
    class SilenceProcess:
        provenance={'engine':'diart','version':'test transport only'}
        async def exchange(self,request): return {'speakers': [],'turns': []}
    async def check():
        buffer=DiarizationBuffer();events=[]
        async def emit(event): events.append(event)
        task=asyncio.create_task(run_diarization(SilenceProcess(),buffer,7,emit))
        for i in range(63):
            buffer.push(b'\0\0'*3200)
            await asyncio.sleep(0)
        buffer.finish();await task
        state=DiarizationState(7)
        for update in events[:-1]:state.apply(update,201600)
        state.finish(events[-1],201600)
        assert state.horizon==state.stable==201600 and not state.turns
        assert any(e['type']=='diarization.update' and e['horizon_samples']==80000 for e in events)
    asyncio.run(check())


def test_v2_explicit_options_no_silent_downgrade(world,monkeypatch):
    from api import live_routes
    base={'project_id':'p'}
    for invalid in ({'protocol':2},{'diarize':True},{'protocol':True},{'protocol':2,'diarize':True,'min_speakers':2}):
        assert world.client.post('/transcribe/live/sessions',json={**base,**invalid}).status_code==422
    response=world.client.post('/transcribe/live/sessions',json={**base,'protocol':2,'diarize':True})
    assert response.status_code==503
    monkeypatch.setattr(live_routes.get_settings(),'live_diarization_enabled',True)
    monkeypatch.setattr(live_routes.get_settings(),'live_diarization_qualified',True)
    assert world.client.post('/transcribe/live/sessions',json={**base,'protocol':2,'diarize':True}).status_code==503
    ready=world.store.readiness();ready['capabilities']=['online_diarization'];world.store.ready(ready)
    response=world.client.post('/transcribe/live/sessions',json={**base,'protocol':2,'diarize':True})
    assert response.status_code==201 and response.json()['protocol']==2
    job=response.json()['job_id'];lease=world.store.lease(job)
    assert lease['protocol']==2 and lease['generation'] < 2**53
    ready['capabilities']=[];world.store.ready(ready)
    assert not world.store.valid(job,lease['generation'])


def test_shared_reference_fixture():
    fixture=json.loads((Path(__file__).parent/'fixtures/live-speakers-v2.json').read_text())
    state=DiarizationState(fixture['generation'])
    for update in fixture['updates']:state.apply(update,fixture['received_samples'])
    assert state.canonical()==fixture['canonical']
    assert state.digest()==fixture['digest']


def enable_v2(world,monkeypatch):
    from api import live_routes
    for key in ('live_diarization_enabled','live_diarization_qualified'):
        monkeypatch.setattr(live_routes.get_settings(),key,True)
    ready=world.store.readiness();ready['capabilities']=['online_diarization'];world.store.ready(ready)
    return world.client.post('/transcribe/live/sessions',json={'project_id':'p','protocol':2,'diarize':True}).json()


def test_ws_v2_speaker_before_finish_digest_durable_equality(world,monkeypatch):
    import websockets
    from tests.test_live_transcription import FakeWorkerSocket,frame
    class Worker(FakeWorkerSocket):
        async def send(self,payload):
            if isinstance(payload,bytes):
                self.clock.accept(payload)
                update=event(horizon=self.clock.samples,turns=[turn(0,self.clock.samples)],stable=0)
                update['generation']=self.generation
                self.speakers.apply(update,self.clock.samples)
                await self.events.put(update)
                await self.events.put({'type':'transcript.final','segment_id':0,'start':0,'end':self.clock.samples/16000,'text':'Olá'})
            else:
                value=json.loads(payload)
                if 'generation' in value:
                    self.generation=value['generation'];self.speakers=DiarizationState(self.generation)
                    await self.events.put({'type':'session.ready','protocol':2,'generation':self.generation,'provider':'whisperx'})
                else:
                    self.clock.finish(value)
                    update=event(2,horizon=self.clock.samples,lo=self.clock.samples,stable=self.clock.samples)
                    update['generation']=self.generation
                    self.speakers.apply(update,self.clock.samples)
                    await self.events.put(update)
                    await self.events.put({'type':'diarization.completed','generation':self.generation,'revision':2,
                        'samples':self.clock.samples,'turn_count':1,'digest':self.speakers.digest(),'provenance':{'engine':'diart'}})
                    await self.events.put({'type':'decoder.completed','samples':self.clock.samples,'inference_seconds':.03})
    worker=Worker();monkeypatch.setattr(websockets,'connect',lambda *a,**k:worker)
    data=enable_v2(world,monkeypatch)
    with world.client.websocket_connect(f"/transcribe/live/sessions/{data['job_id']}/stream") as ws:
        ws.send_json({'type':'authenticate','protocol':2,'ticket':data['ticket']})
        assert ws.receive_json()['protocol']==2
        ws.send_bytes(frame(0,0))
        update,confirmed=ws.receive_json(),ws.receive_json()
        assert update['type']=='diarization.update' and confirmed['text']=='Olá'
        ws.send_json({'type':'finish','last_seq':0})
        frozen,complete=ws.receive_json(),ws.receive_json()
        assert frozen['stable_until_samples']==3200
        assert complete['type']=='session.completed',complete
        assert complete['diarization_digest']==worker.speakers.digest()
    world.redis.client.delete(f"job:{data['job_id']}:result")
    result=world.client.get(f"/jobs/{data['job_id']}/result?format=json").json()
    assert result['schema_version']==2
    assert result['segments'][0]['speaker_id']=='SPEAKER_00'
    assert result['segments'][0]['text']==confirmed['text']
    assert result['diarization']['turns']==[{'start':0,'end':.2,'speaker_id':'SPEAKER_00'}]


def test_ws_v2_cannot_authenticate_v1_lease(world):
    data=world.client.post('/transcribe/live/sessions',json={'project_id':'p'}).json()
    with world.client.websocket_connect(f"/transcribe/live/sessions/{data['job_id']}/stream") as ws:
        ws.send_json({'type':'authenticate','protocol':2,'ticket':data['ticket']})
        assert ws.receive_json()['code']=='LIVE_INVALID_TICKET'


def test_online_asr_adapter_preserves_native_timestamp_arguments():
    from types import SimpleNamespace
    from workers.live.decoder import WhisperXOnlineASR
    calls=[]
    def transcribe(audio,**options):calls.append((audio,options));return iter([]),None
    adapter=WhisperXOnlineASR(SimpleNamespace(model=SimpleNamespace(transcribe=transcribe)))
    adapter.transcribe(b'pcm',word_timestamps=True,initial_prompt='context')
    assert calls==[(b'pcm',{'word_timestamps':True,'initial_prompt':'context'})]


def test_isolated_inference_timeout_terminates_process_before_reuse():
    import sys
    from workers.live.diarizer import DiartProcess
    async def check():
        child=DiartProcess(sys.executable,'unused')
        child.process=await asyncio.create_subprocess_exec(sys.executable,'-c','import time; time.sleep(60)',
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
        child.ready=child.busy=True
        with pytest.raises(LiveError,match='LIVE_DIARIZATION_TIMEOUT'):
            await child.exchange({'type':'infer'},timeout=.02)
        assert not child.ready and child.busy
        await child.release()
        assert child.process.returncode is not None and not child.busy
    asyncio.run(check())


def test_cancel_during_isolated_inference_waits_for_real_process_death():
    import sys
    from workers.live.diarizer import DiartProcess
    async def check():
        child=DiartProcess(sys.executable,'unused')
        child.process=await asyncio.create_subprocess_exec(sys.executable,'-c','import time; time.sleep(60)',
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
        child.ready=child.busy=True
        operation=asyncio.create_task(child.exchange({'type':'infer'}))
        await asyncio.sleep(.01)
        operation.cancel()
        with pytest.raises(asyncio.CancelledError): await operation
        assert child.busy and not child.ready
        await child.release()
        assert child.process.returncode is not None and not child.busy
    asyncio.run(check())


def test_child_crash_removes_readiness_and_never_returns_empty_success():
    import sys
    from workers.live.diarizer import DiartProcess
    async def check():
        child=DiartProcess(sys.executable,'unused')
        child.process=await asyncio.create_subprocess_exec(sys.executable,'-c','pass',
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
        child.ready=child.busy=True
        with pytest.raises(LiveError,match='LIVE_DIARIZATION_FAILED'):
            await child.exchange({'type':'infer'})
        assert not child.ready
        await child.release()
        assert child.process.returncode is not None and not child.busy
    asyncio.run(check())


def test_partial_online_pool_warmup_limits_admission_without_blocking_v1(world):
    ready=world.store.readiness();ready.update(capacity=3,diarization_capacity=1,capabilities=['online_diarization'])
    world.store.ready(ready)
    world.store.reserve('v1',protocol=1)
    world.store.reserve('v2',protocol=2)
    with pytest.raises(LiveError,match='LIVE_DIARIZATION_NOT_READY'):
        world.store.reserve('too-many-online',protocol=2)
    world.store.reserve('another-v1',protocol=1)


def test_online_declared_budget_failure_does_not_fail_asr_budget(world):
    from types import SimpleNamespace
    from shared.live.capacity import require_production_budget
    from shared.models import Engine
    settings=SimpleNamespace(live_gpu_ref='gpu0',live_vram_footprint_gb=3,live_vram_reserve_gb=3.2,
        live_diarization_enabled=True,live_diarization_gpu_gb=8,live_max_sessions=1,
        vision_model_id='florence-community/Florence-2-base-ft')
    with world.db() as db:
        db.add(Engine(id='engine',slug='local',display_name='Local',adapter_type='local',config={
            'gpus':[{'ref':'gpu0','uuid':'GPU-test','vram_gb':16,'vram_reserve_gb':2}],
            'features':{'transcription':{'gpu_ref':'gpu0','workers':2,'executions_per_worker':1}}}))
        db.commit()
        assert require_production_budget(db,settings,{'uuid':'GPU-test'}).fits
        with pytest.raises(RuntimeError,match='does not fit'):
            require_production_budget(db,settings,{'uuid':'GPU-test'},include_diarization=True)
