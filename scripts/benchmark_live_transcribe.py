#!/usr/bin/env python3
"""Live replay at 1x; send only after each frame's last sample is available.

Credentials are read from LIVE_API_KEY or LIVE_BEARER_TOKEN, never CLI/URLs.
Reference machine transcripts are comparison aids, not human WER ground truth.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import time

RATE = 16000


class SpeakerEvidence:
    """Receiver evidence only; this does not measure browser rendering or DER."""

    def __init__(self):
        self.state = None

    def ready(self, event):
        backend = str(Path(__file__).resolve().parents[1] / 'backend')
        if backend not in sys.path:
            sys.path.insert(0, backend)
        from shared.live.diarization import DiarizationState
        if self.state is not None or event.get('protocol') != 2:
            raise RuntimeError('Unexpected speaker protocol negotiation')
        self.state = DiarizationState(event.get('generation'))

    def update(self, event, sent_samples):
        if self.state is None:
            raise RuntimeError('Speaker event arrived before readiness')
        self.state.apply(event, sent_samples)

    def completed(self, event, sent_samples):
        if (self.state is None or self.state.horizon != sent_samples
                or self.state.stable != sent_samples
                or event.get('diarization_digest') != self.state.digest()):
            raise RuntimeError('Completed speaker state does not match the received PCM clock/digest')

    def validate_result(self, payload, finals):
        from shared.live.diarization import annotate_result
        expected = annotate_result(self.state, {'segments': transcript_segments(finals)}, {})
        if (payload.get('schema_version') != 2 or payload.get('speakers') != expected['speakers']
                or payload.get('segments') != expected['segments']):
            raise RuntimeError('Persisted speaker transcript differs from received state')
        actual, wanted = payload.get('diarization', {}), expected['diarization']
        for field in ('status', 'speaker_count', 'generation', 'revision', 'turns'):
            if actual.get(field) != wanted[field]:
                raise RuntimeError('Persisted speaker intervals differ from received state')


def transcript_segments(segments):
    return [{k: segment[k] for k in ('start', 'end', 'text')} for segment in segments]


async def wait_for_event(event, receiver, timeout):
    """Surface receive/validation failures immediately, without a false timeout."""
    waiter = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait({waiter, receiver}, timeout=timeout,
                                     return_when=asyncio.FIRST_COMPLETED)
        if receiver in done:
            receiver.result()  # Propagate a corrupt event stream or disconnect.
        if not event.is_set():
            if not done:
                raise TimeoutError('Live event deadline exceeded')
            raise RuntimeError('Receiver stopped before the expected live event')
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


def load_pcm(path):
    if not path.is_file():
        raise SystemExit('Fixture missing. Supply --audio with local mono16k s16le PCM or media; no audio is downloaded.')
    if path.suffix.lower() == '.pcm':
        data = path.read_bytes()
    else:
        result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 's16le', '-ar', '16000',
            '-ac', '1', 'pipe:1'], capture_output=True, check=True)
        data = result.stdout
    if not data or len(data) % 2:
        raise SystemExit('Fixture must contain complete nonempty signed16 samples')
    return data


def percentile(values, quantile=.95):
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * quantile))]


async def replay(args):
    import httpx
    import websockets
    from urllib.parse import urlsplit
    url = urlsplit(args.api_url)
    if url.username or url.password or url.query or url.fragment:
        raise SystemExit('API URL must not contain credentials or query parameters')
    bearer, key = os.environ.get('LIVE_BEARER_TOKEN'), os.environ.get('LIVE_API_KEY')
    if not bearer and not key:
        raise SystemExit('Set LIVE_BEARER_TOKEN or LIVE_API_KEY in the environment')
    headers = {'Authorization': 'Bearer ' + bearer} if bearer else {'X-API-Key': key}
    data = load_pcm(Path(args.audio))
    if args.seconds is not None:
        if not math.isfinite(args.seconds) or args.seconds <= 0:
            raise SystemExit('--seconds must be finite and positive')
        data = data[:int(args.seconds * RATE) * 2]
    if not data:
        raise SystemExit('Selected audio must contain at least one sample')
    duration = len(data) / (2 * RATE)
    protocol = 2 if getattr(args, 'diarize', False) else 1
    speakers = SpeakerEvidence() if protocol == 2 else None
    events, delays, finals, frames = [], [], [], []
    report = {'audio_sha256': hashlib.sha256(data).hexdigest(), 'audio_seconds': duration,
              'protocol': protocol, 'replay_speed': 1, 'quality_reference': 'not-human-reviewed',
              'quality_gate': 'not-evaluated', 'cold_or_warm': args.phase,
              'inference_measurement_scope': 'asr-only'}
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(args.api_url.rstrip('/') + '/transcribe/live/sessions', headers=headers,
            json={'project': args.project, 'name': 'Benchmark live 1x', 'language': 'pt',
                  'protocol': protocol, 'diarize': protocol == 2})
        if response.status_code != 201:
            raise SystemExit(f'Admission failed with HTTP{response.status_code}; no automatic retry or capacity override')
        session = response.json()
        report['creation_seconds'] = time.monotonic() - started
        report['job_id'] = session['job_id']
        ready = asyncio.Event()
        completed = asyncio.Event()
        t0 = None
        sent_samples = 0
        error = None
        seq = 0
        async with websockets.connect(session['ws_url'], max_size=65536, max_queue=32) as socket:
            await socket.send(json.dumps({'type': 'authenticate', 'protocol': protocol, 'ticket': session['ticket']}))

            async def receive():
                nonlocal error
                previous_event = 0
                async for payload in socket:
                    event = json.loads(payload)
                    if event['event_seq'] != previous_event + 1:
                        raise RuntimeError('Event sequence was lost or duplicated')
                    previous_event = event['event_seq']
                    elapsed = time.monotonic() - t0 if t0 is not None else None
                    # Tickets and payload audio are never saved/logged.
                    events.append({**event, 'client_elapsed_seconds': elapsed,
                                   'client_sent_samples': sent_samples})
                    if event['type'] == 'session.ready':
                        if speakers:
                            speakers.ready(event)
                        report['backend'], report['model'] = event['backend'], event['model']
                        report['compute_type'] = event.get('compute_type')
                        report['worker_cold_start_seconds'] = event.get('cold_start_seconds')
                        ready.set()
                    elif event['type'] == 'transcript.final':
                        finals.append(event)
                    elif event['type'] == 'diarization.update':
                        if speakers is None:
                            raise RuntimeError('Unnegotiated speaker event')
                        speakers.update(event, sent_samples)
                    elif event['type'] == 'session.error':
                        error = event['code']; ready.set(); completed.set(); return
                    elif event['type'] == 'session.completed':
                        if speakers:
                            speakers.completed(event, sent_samples)
                        report['inference_seconds'] = event.get('inference_seconds')
                        report['inference_rtf'] = (event['inference_seconds'] / duration) if event.get('inference_seconds') is not None else None
                        completed.set(); return
                if not completed.is_set():
                    error = 'LIVE_CONNECTION_CLOSED'; ready.set(); completed.set()

            receiver = asyncio.create_task(receive())
            try:
                await wait_for_event(ready, receiver, 15)
                if error:
                    raise RuntimeError(error)
                t0 = time.monotonic()
                for offset in range(0, len(data), 6400):
                    pcm = data[offset:offset + 6400]
                    deadline = t0 + (sent_samples + len(pcm) // 2) / RATE
                    wait = deadline - time.monotonic()
                    if wait > 0:
                        await asyncio.sleep(wait)
                    late = max(0, time.monotonic() - deadline)
                    delays.append(late)
                    # A stalled client cannot prove 1x by sending catch-up bursts.
                    if late > .2:
                        raise RuntimeError('Replay client missed a frame deadline by >200ms; refusing catch-up burst')
                    if error:
                        break
                    if receiver.done():
                        receiver.result()
                        raise RuntimeError('Receiver stopped while sending audio')
                    frame = struct.pack('<IQ', seq, sent_samples) + pcm
                    sent_samples += len(pcm) // 2
                    sent_at = time.monotonic() - t0
                    await socket.send(frame)
                    frames.append({'seq': seq, 'end_samples': sent_samples,
                                   'send_started_seconds': sent_at,
                                   'send_completed_seconds': time.monotonic() - t0})
                    seq += 1
                eof = time.monotonic()
                if not error:
                    report['finish_sent_seconds'] = eof - t0
                    await socket.send(json.dumps({'type': 'finish', 'last_seq': seq - 1}))
                    await wait_for_event(completed, receiver, 30 if speakers else 120)
                report['finalization_seconds'] = time.monotonic() - eof
            except Exception as exc:
                error = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                with __import__('contextlib').suppress(Exception):
                    await client.delete(args.api_url.rstrip('/') + '/transcribe/live/sessions/' + session['job_id'], headers=headers)
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
        if not error:
            try:
                result = await client.get(args.api_url.rstrip('/') + '/jobs/' + session['job_id'] + '/result?format=json', headers=headers)
                result.raise_for_status()
                final_payload = result.json()
                if transcript_segments(final_payload['segments']) != transcript_segments(finals):
                    raise RuntimeError('Persisted transcript differs from immutable WS finals')
                if speakers:
                    speakers.validate_result(final_payload, finals)
                    report['persisted_speakers_match_events'] = True
                    report['speaker_state_digest'] = speakers.state.digest()
                    report['speaker_count'] = len(speakers.state.speakers)
                report['persisted_final_matches_events'] = True
            except Exception as exc:
                error = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    first = next((e for e in events if e['type'] in ('transcript.partial', 'transcript.final') and e.get('text')), None)
    lags = [e['client_elapsed_seconds'] - e['end'] for e in events if e['type'] == 'transcript.final' and e['client_elapsed_seconds'] is not None]
    report.update({'outcome': 'failed' if error else 'completed', 'error': error,
        'first_caption_seconds_from_capture_start': first['client_elapsed_seconds'] if first else None,
        'confirmed_lag_p95_seconds_model_timestamps': percentile(lags),
        'client_send_lag_p95_seconds': percentile(delays), 'frames_sent': seq,
        'final_segments': len(finals), 'events': events, 'frames': frames,
        'backlog_max_seconds': max((e.get('backlog_seconds', 0) for e in events), default=0),
        'latency_reference': 'model timestamps, not manually aligned speech onset',
        'release_gate': 'not-approved: human WER, cold/warm repetitions, Voxtral comparison and shared GPU concurrency still required'})
    if speakers:
        labelled = [event for event in events if event['type'] == 'diarization.update' and event.get('turns')]
        before_eof = [event for event in labelled if event['client_elapsed_seconds'] is not None
                      and event['client_elapsed_seconds'] < report.get('finish_sent_seconds', -1)]
        report.update({'first_speaker_seconds_from_capture_start': labelled[0]['client_elapsed_seconds'] if labelled else None,
                       'speaker_updates_before_finish': len(before_eof),
                       'speaker_labels_observed_before_finish': bool(before_eof),
                       'speaker_observation_reference': 'WebSocket receiver, not rendered browser UI or human speech onset',
                       'release_gate': 'not-approved: human-reference DER/WER, causal browser snapshots, cold/warm repetitions, CUDA and shared GPU concurrency still required'})
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('events', 'frames')}, ensure_ascii=False))
    return 1 if error else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True)
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--phase', choices=['cold', 'warm'], default='warm')
    parser.add_argument('--diarize', action='store_true', help='Negotiate protocol 2 and verify speaker events/durable result')
    parser.add_argument('--output', default='live-benchmark.json')
    raise SystemExit(asyncio.run(replay(parser.parse_args())))
