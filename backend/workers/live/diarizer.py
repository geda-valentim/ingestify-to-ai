"""Bounded scheduling and lifecycle for the isolated, warmed Diart process."""
import asyncio
import base64
import json
import os
from pathlib import Path
import secrets
import struct
from contextlib import suppress

from shared.live.protocol import LiveError, RATE
from shared.live.diarization import DiarizationState, canonical_turns

WINDOW = 5 * RATE
STEP = RATE // 2
MAX_BACKLOG = 2 * RATE


class DiarizationBuffer:
    """A is incorporated PCM; H is the last inference decision boundary.

The five seconds of initial context do not constitute pending inference. A job
becomes eligible only at a complete window; an in-flight job counts until done.
"""
    def __init__(self):
        self.audio = bytearray()
        self.offset = self.incorporated = self.horizon = 0
        self.next_step = WINDOW
        self.pending = []
        self.finished = False
        self.changed = asyncio.Event()

    def push(self, pcm):
        if self.finished:
            raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)
        self.audio.extend(pcm)
        self.incorporated += len(pcm) // 2
        while self.next_step <= self.incorporated:
            self.pending.append((self.next_step, False))
            self.next_step += STEP
        if len(self.pending) * STEP >= MAX_BACKLOG or len(self.audio) > 10 * RATE * 2:
            raise LiveError('LIVE_DIARIZATION_BACKPRESSURE', 4429)
        if self.incorporated >= 6 * RATE and self.horizon == 0:
            raise LiveError('LIVE_DIARIZATION_TIMEOUT', 1011)
        self.changed.set()

    def finish(self):
        self.finished = True
        if not self.pending or self.pending[-1][0] != self.incorporated:
            if self.horizon != self.incorporated:
                self.pending.append((max(WINDOW, self.next_step), True))
        self.changed.set()

    def window(self, step):
        end, final = step
        offset = max(0, end - WINDOW)
        start = (offset - self.offset) * 2
        if start < 0:
            raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)
        pcm = bytes(self.audio[start:start + WINDOW * 2])
        return pcm + b'\0' * (WINDOW * 2 - len(pcm)), offset, min(end, self.incorporated)

    def complete(self, end, horizon):
        if not self.pending or self.pending[0][0] != end:
            raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)
        self.pending.pop(0)
        self.horizon = horizon
        keep = max(0, (self.pending[0][0] if self.pending else self.next_step) - WINDOW)
        trim = max(0, min(keep, self.incorporated) - self.offset)
        del self.audio[:trim * 2]
        self.offset += trim

    def clear(self):
        self.audio[:] = b'\0' * len(self.audio)
        self.audio.clear()
        self.pending.clear()


class DiartProcess:
    def __init__(self, python, manifest):
        self.python, self.manifest = python, manifest
        self.process = None
        self.ready = False
        self.busy = False
        self.nonce = secrets.token_urlsafe(32)
        self.provenance = None

    async def exchange(self, message, timeout=2):
        async def operation():
            payload = json.dumps({**message, 'nonce': self.nonce}, separators=(',', ':')).encode()
            if len(payload) > 256_000:
                raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)
            self.process.stdin.write(struct.pack('!I', len(payload)) + payload)
            await self.process.stdin.drain()
            length = struct.unpack('!I', await self.process.stdout.readexactly(4))[0]
            if length > 65536:
                raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)
            value = json.loads(await self.process.stdout.readexactly(length))
            if value.get('nonce') != self.nonce:
                raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)
            if value.get('type') == 'error':
                code = value.get('code')
                allowed = {'LIVE_DIARIZATION_SPEAKER_LIMIT', 'LIVE_DIARIZATION_TURN_LIMIT'}
                raise LiveError(code if code in allowed else 'LIVE_DIARIZATION_FAILED', 1011)
            return value
        try:
            return await asyncio.wait_for(operation(), timeout)
        except asyncio.TimeoutError:
            self.ready = False
            raise LiveError('LIVE_DIARIZATION_TIMEOUT', 1011) from None
        except LiveError:
            self.ready = False
            raise
        except asyncio.CancelledError:
            self.ready = False
            raise
        except Exception:
            self.ready = False
            raise LiveError('LIVE_DIARIZATION_FAILED', 1011) from None

    async def start(self):
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'TMPDIR', 'LD_LIBRARY_PATH', 'LANG')
               or k.startswith(('CUDA_', 'NVIDIA_', 'LC_'))}
        env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2')
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
        self.process = await asyncio.create_subprocess_exec(self.python, '-m', 'workers.live.diart_process',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=env, limit=65536)
        try:
            result = await self.exchange({'type': 'boot', 'manifest': self.manifest}, timeout=120)
            if result.get('type') != 'ready':
                raise LiveError('LIVE_DIARIZATION_NOT_READY', 1013)
            self.provenance = result['provenance']
            self.ready = True
        except BaseException:
            await self.close()
            raise

    async def close(self):
        self.ready = False
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 2)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

    async def release(self):
        try:
            if self.ready and self.process.returncode is None:
                await self.exchange({'type': 'reset'})
            else:
                await self.close()
        except BaseException:
            await self.close()
        finally:
            self.busy = False

    def acquire(self):
        if not self.ready or self.busy or self.process.returncode is not None:
            raise LiveError('LIVE_DIARIZATION_NOT_READY', 1013)
        self.busy = True
        return self


async def run_diarization(process, buffer, generation, emit):
    state = DiarizationState(generation)
    try:
        while True:
            if not buffer.pending:
                if buffer.finished:
                    break
                buffer.changed.clear()
                await buffer.changed.wait()
                continue
            step = buffer.pending[0]
            pcm, offset, horizon = buffer.window(step)
            response = await process.exchange({'type': 'infer', 'pcm': base64.b64encode(pcm).decode(),
                'offset': offset, 'horizon': horizon, 'stable': state.stable})
            event = {'type': 'diarization.update', 'generation': generation, 'revision': state.revision + 1,
                'horizon_samples': horizon, 'replace_from_samples': max(state.stable, horizon - WINDOW, 0),
                'replace_to_samples': horizon, 'stable_until_samples': max(state.stable, horizon - RATE, 0),
                'speakers': response['speakers'], 'turns': response['turns']}
            state.apply(event, buffer.incorporated)
            buffer.complete(step[0], horizon)
            await emit(event)
        # Freeze existing annotations, including silence and a zero-length capture.
        event = {'type': 'diarization.update', 'generation': generation, 'revision': state.revision + 1,
            'horizon_samples': buffer.incorporated, 'replace_from_samples': buffer.incorporated,
            'replace_to_samples': buffer.incorporated, 'stable_until_samples': buffer.incorporated,
            'speakers': state.speakers, 'turns': []}
        state.apply(event, buffer.incorporated)
        await emit(event)
        await emit({'type': 'diarization.completed', 'generation': generation, 'revision': state.revision,
            'samples': buffer.incorporated, 'turn_count': len(canonical_turns(state.turns)),
            'digest': state.digest(), 'provenance': process.provenance})
    finally:
        buffer.clear()
