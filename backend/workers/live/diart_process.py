"""Private Diart subprocess entry point, launched with its own locked Python.

Only inherited anonymous pipes carry PCM. No listening port or downloaded model,
no token in arguments. The parent supplies a per-process nonce on the first frame.
"""
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import struct
import sys

MAX_MESSAGE = 256_000
HEADER = struct.Struct('!I')


def read_message(stream):
    header = stream.read(4)
    if not header:
        raise EOFError
    if len(header) != 4:
        raise ValueError('truncated private frame')
    length = HEADER.unpack(header)[0]
    if length > MAX_MESSAGE:
        raise ValueError('oversized private frame')
    payload = stream.read(length)
    if len(payload) != length:
        raise ValueError('truncated private frame')
    return json.loads(payload)


def send_message(stream, value):
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    if len(payload) > MAX_MESSAGE:
        raise ValueError('oversized private frame')
    stream.write(HEADER.pack(len(payload)) + payload)
    stream.flush()


def model_manifest(path):
    value = json.loads(Path(path).read_text())
    if value.get('schema_version') != 1 or value.get('diart_version') != '0.9.2':
        raise ValueError('unsupported Diart manifest')
    for key in ('segmentation', 'embedding'):
        entry = value[key]
        if any(not isinstance(entry.get(field), str) or not 1 <= len(entry[field]) <= 200 for field in ('model_id', 'license')):
            raise ValueError('model identity and license are required')
        checkpoint = Path(entry['path'])
        if not checkpoint.is_absolute() or not checkpoint.is_file() or not re.fullmatch('[0-9a-f]{40}', entry['revision']):
            raise ValueError('unprovisioned model')
        with checkpoint.open('rb') as model_file:
            digest = hashlib.file_digest(model_file, 'sha256').hexdigest()
        if digest != entry['sha256']:
            raise ValueError('model checksum mismatch')
    return value


def checkpoint_globals():
    """Pinned Pyannote 3 checkpoint metadata allowed by Torch 2.8's safe loader.

    Do not disable weights_only or globally replace torch.load. This context is
    entered only after local checkpoint hashes were verified by model_manifest.
    Additional unrecognized pickle objects fail qualification explicitly.
    """
    from pyannote.audio.core.task import Specifications, Problem, Resolution
    from torch.torch_version import TorchVersion
    return [Specifications, Problem, Resolution, TorchVersion]


class DiartSession:
    def __init__(self, manifest, device='cuda'):
        import torch
        import numpy as np
        from diart import SpeakerDiarization, SpeakerDiarizationConfig
        from diart.models import SegmentationModel, EmbeddingModel
        if importlib.metadata.version('diart') != manifest['diart_version']:
            raise ValueError('Diart version mismatch')
        if device != 'cuda' or not torch.cuda.is_available():
            raise ValueError('live requires CUDA')
        with torch.serialization.safe_globals(checkpoint_globals()):
            config = SpeakerDiarizationConfig(
                segmentation=SegmentationModel.from_pyannote(manifest['segmentation']['path'], use_hf_token=False),
                embedding=EmbeddingModel.from_pyannote(manifest['embedding']['path'], use_hf_token=False),
                duration=5, step=.5, latency=1, max_speakers=20, device=torch.device(device))
            self.pipeline = SpeakerDiarization(config)
            self.reset()
            self.infer(b'\0\0' * 80_000, 0, 80_000, 0)
            self.reset()  # Warmup must not seed a user's voice catalog.
        self.provenance = {'engine': 'diart', 'version': manifest['diart_version'],
            'clustering': 'evidence-v1', 'segmentation_revision': manifest['segmentation']['revision'],
            'embedding_revision': manifest['embedding']['revision'],
            'segmentation_model': manifest['segmentation']['model_id'],
            'embedding_model': manifest['embedding']['model_id'], 'window_seconds': 5,
            'step_seconds': .5, 'latency_seconds': 1}

    def reset(self):
        from workers.live.diart_clustering import EvidenceClustering
        old = getattr(self.pipeline, 'clustering', None)
        if hasattr(old, 'clear'):
            old.clear()
        self.pipeline.reset()
        config = self.pipeline.config
        self.pipeline.clustering = EvidenceClustering(config.tau_active, config.rho_update, config.delta_new,
                                                     'cosine', config.max_speakers)

    def infer(self, pcm, offset, horizon, stable):
        import numpy as np
        import torch
        from pyannote.core import SlidingWindowFeature, SlidingWindow
        from shared.live.protocol import RATE
        data = np.frombuffer(pcm, dtype='<i2').astype(np.float32).reshape(-1, 1) / 32768
        if data.shape != (80_000, 1):
            raise ValueError('invalid window')
        waveform = SlidingWindowFeature(data, SlidingWindow(start=offset / RATE, duration=1 / RATE, step=1 / RATE))
        with torch.inference_mode():
            annotation, _ = self.pipeline([waveform])[0]
            # The newest suffix is provisional. Reuse Diart's official aggregation
            # where available and its pre-aggregation decisions for the recent tail.
            latest = self.pipeline.binarize(self.pipeline.clustering.latest)
        def turns(ann, lo, hi):
            result = []
            for segment, _, label in ann.itertracks(yield_label=True):
                a, b = max(lo, round(segment.start * RATE)), min(hi, round(segment.end * RATE))
                if a < b:
                    # Diart Binarize emits speaker0, speaker1, ...
                    index = int(str(label).removeprefix('speaker'))
                    result.append({'start_samples': a, 'end_samples': b, 'speaker_id': f'SPEAKER_{index:02d}'})
            return result
        lo = max(stable, horizon - 80_000, 0)
        aggregate_end = min(horizon, max(0, offset + 72_000))
        # The first window aggregates the prefix; subsequent windows aggregate
        # [window_end-1s, window_end-.5s). Earlier revisable output uses this
        # window's evidence and cannot modify already frozen annotations.
        aggregate_start = max(lo, 0 if offset == 0 else offset + 64_000)
        output = turns(latest, lo, min(aggregate_start, horizon))
        output += turns(annotation, aggregate_start, aggregate_end)
        output += turns(latest, max(aggregate_end, lo), horizon)
        from shared.live.diarization import canonical_turns
        output = canonical_turns(output)
        if len(output) > 64:
            raise ValueError('too many window turns')
        count = self.pipeline.clustering.num_known_speakers
        return {'turns': output, 'speakers': [{'id': f'SPEAKER_{i:02d}', 'label': f'Falante {i + 1}'} for i in range(count)]}


def main():
    # Third-party diagnostic print calls must never corrupt the private pipe.
    source, destination = sys.stdin.buffer, sys.stdout.buffer
    sys.stdout = sys.stderr
    boot = read_message(source)
    nonce = boot['nonce']
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    session = DiartSession(model_manifest(boot['manifest']))
    send_message(destination, {'type': 'ready', 'nonce': nonce, 'provenance': session.provenance})
    while True:
        request = read_message(source)
        if request.get('nonce') != nonce:
            raise ValueError('private authentication failed')
        if request['type'] == 'reset':
            session.reset()
            response = {'type': 'reset'}
        else:
            pcm = base64.b64decode(request['pcm'], validate=True)
            try:
                response = session.infer(pcm, request['offset'], request['horizon'], request['stable'])
            except Exception as exc:
                send_message(destination, {'type': 'error', 'nonce': nonce, 'code': getattr(exc, 'code', 'LIVE_DIARIZATION_FAILED')})
                raise
        send_message(destination, {**response, 'nonce': nonce})


if __name__ == '__main__':
    try:
        main()
    except EOFError:
        pass
    except Exception:
        # Details may contain a private filesystem location; parent reports only
        # the typed unavailable/failed code, never child exception content.
        sys.exit(1)
