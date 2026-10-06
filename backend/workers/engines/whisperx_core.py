"""WhisperX 3.8.6 file pipeline. No settings, database, Celery or remote SDK.

Models are provisioned offline. The iterator adapter uses the upstream VAD and
batch iterator; it does not turn percentage callbacks into invented segments.
A fresh shallow wrapper/tokenizer/options is used for each execution, sharing
only model weights. A lock serializes the mutable VAD's use of those weights.
"""
from copy import copy
from dataclasses import replace
import gc
import importlib.metadata
import json
import re
from pathlib import Path
import threading
import time

from workers.engines.transcript_schema import normalize_aligned_segments, validate_result

VERSION = '3.8.6'


class TranscriptionCancelled(RuntimeError):
    pass


class WhisperXError(RuntimeError):
    def __init__(self, code, detail=''):
        self.code = code
        super().__init__(f'{code}: {detail}' if detail else code)


def _check_cancel(should_cancel):
    if should_cancel and should_cancel():
        raise TranscriptionCancelled('transcription cancelled or deadline exceeded')


def iter_asr_segments(pipeline, audio, options, *, batch_size=1, should_cancel=None):
    """Narrow adapter over the pinned pipeline's real generator of decoded batches."""
    from faster_whisper.tokenizer import Tokenizer
    from whisperx.vads import Vad
    if not isinstance(pipeline.vad_model, Vad):
        raise WhisperXError('UNSUPPORTED_VAD', 'only provisioned WhisperX VAD adapters are supported')
    wrapper = copy(pipeline)
    wrapper.options = replace(pipeline.options, beam_size=int(options.get('beam_size', 5)),
                              temperatures=[float(options.get('temperature', 0.0))])
    wrapper._forward_params = dict(pipeline._forward_params)
    wrapper._preprocess_params = dict(pipeline._preprocess_params)
    wrapper._postprocess_params = dict(pipeline._postprocess_params)
    language = options.get('language') or wrapper.detect_language(audio)
    wrapper.tokenizer = Tokenizer(wrapper.model.hf_tokenizer, wrapper.model.model.is_multilingual,
                                  task='transcribe', language=language)
    _check_cancel(should_cancel)
    waveform = wrapper.vad_model.preprocess_audio(audio)
    chunks = wrapper.vad_model.merge_chunks(
        wrapper.vad_model({'waveform': waveform, 'sample_rate': 16000}), 30,
        onset=wrapper._vad_params['vad_onset'], offset=wrapper._vad_params['vad_offset'])
    del waveform
    _check_cancel(should_cancel)
    def inputs():
        for chunk in chunks:
            _check_cancel(should_cancel)
            yield {'inputs': audio[int(chunk['start'] * 16000):int(chunk['end'] * 16000)]}
    output = iter(wrapper(inputs(), batch_size=batch_size, num_workers=0))
    for chunk in chunks:
        _check_cancel(should_cancel)
        decoded = next(output)
        _check_cancel(should_cancel)
        text = decoded['text']
        if isinstance(text, list):
            text = text[0]
        yield {'start': float(chunk['start']), 'end': float(chunk['end']), 'text': str(text)}, language


def load_bounded_audio(path, maximum_seconds):
    """Bound decoded PCM before allocating, including misleading input metadata."""
    import numpy as np
    import subprocess
    process = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
        '-t', str(maximum_seconds + 1), '-f', 'f32le', '-acodec', 'pcm_f32le',
        '-ac', '1', '-ar', '16000', '-'], capture_output=True, check=True)
    audio = np.frombuffer(process.stdout, dtype=np.float32).copy()
    if len(audio) > maximum_seconds * 16000:
        raise WhisperXError('AUDIO_DURATION_LIMIT_EXCEEDED')
    return audio


def offline_silero(path):
    """Use the pinned local Silero repository, avoiding upstream torch.hub network."""
    import torch
    from whisperx.vads import Silero
    class LocalSilero(Silero):
        def __init__(self):
            self.vad_onset, self.chunk_size = 0.5, 30
            self.vad_pipeline, utilities = torch.hub.load(repo_or_dir=path,
                model='silero_vad', source='local', onnx=False)
            self.get_speech_timestamps, _, self.read_audio, _, _ = utilities
    return LocalSilero()


class WhisperXRuntime:
    def __init__(self, model_dir, device='cpu', compute_type='int8', *, batch_size=1,
                 max_audio_seconds=7200, allow_unqualified=False):
        if importlib.metadata.version('whisperx') != VERSION:
            raise WhisperXError('WHISPERX_VERSION_MISMATCH', f'requires {VERSION}')
        self.root = Path(model_dir)
        self.manifest = json.loads((self.root / 'manifest.json').read_text())
        if set(self.manifest) - {'asr', 'vad', 'aligners', 'diarizer', 'qualified'}:
            raise WhisperXError('INVALID_MODEL_MANIFEST', 'unexpected manifest fields')
        self.device, self.compute_type = device, compute_type
        self.batch_size = batch_size
        self.max_audio_seconds = max_audio_seconds
        if type(batch_size) is not int or not 1 <= batch_size <= 16:
            raise ValueError('batch_size must be 1..16')
        if not allow_unqualified and not self.manifest.get('qualified'):
            raise WhisperXError('DIARIZATION_NOT_READY', 'model manifest has not passed target qualification')
        self.lock = threading.RLock()
        self.asr = None

    def _path(self, entry):
        path = (self.root / entry['path']).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.exists() or not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', entry.get('revision', '')):
            raise WhisperXError('DIARIZATION_MODEL_UNAVAILABLE', 'invalid offline model manifest')
        return str(path)

    def _load_asr(self):
        import whisperx
        # force offline; credentials are never passed to a job or inference call.
        import os
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        if self.asr is None:
            self.asr = whisperx.load_model(self._path(self.manifest['asr']), self.device,
                compute_type=self.compute_type, vad_method='silero', local_files_only=True,
                vad_model=offline_silero(self._path(self.manifest['vad'])),
                asr_options={'beam_size': 5, 'temperatures': [0.0]},
                vad_options={'vad_onset': 0.5, 'vad_offset': 0.363})
        return self.asr

    def release(self):
        self.asr = None
        gc.collect()
        if self.device.startswith('cuda'):
            import torch
            torch.cuda.empty_cache()

    def transcribe(self, audio_path, options=None, *, on_progress=None, should_cancel=None,
                   on_phase=None, model_name='turbo'):
        import whisperx
        options = dict(options or {})
        should_cancel = should_cancel or options.get('_should_cancel')
        on_phase = on_phase or options.get('_on_phase')
        with self.lock:
            _check_cancel(should_cancel)
            audio = load_bounded_audio(audio_path, self.max_audio_seconds)
            duration = len(audio) / 16000
            if duration > self.max_audio_seconds:
                raise WhisperXError('AUDIO_DURATION_LIMIT_EXCEEDED')
            profile = options.get('transcription_profile')
            if profile:
                expected = profile['models']
                if self.manifest['asr'].get('model', model_name) != expected['asr']:
                    raise WhisperXError('TRANSCRIPTION_PROFILE_MISMATCH', 'ASR model')
                if expected['asr_revision'] != self.manifest['asr']['revision']:
                    raise WhisperXError('TRANSCRIPTION_PROFILE_MISMATCH', 'ASR revision')
                if profile['vad']['revision'] != self.manifest['vad']['revision']:
                    raise WhisperXError('TRANSCRIPTION_PROFILE_MISMATCH', 'VAD revision')
                if options.get('diarize') and expected.get('diarizer_revision') != self.manifest.get('diarizer', {}).get('revision'):
                    raise WhisperXError('TRANSCRIPTION_PROFILE_MISMATCH', 'diarizer revision')
            timings = {}
            def phase(name):
                _check_cancel(should_cancel)
                if on_phase:
                    on_phase(name)
            phase('transcribing')
            started = time.monotonic()
            segments = []
            language = options.get('language')
            for segment, language in iter_asr_segments(self._load_asr(), audio, options,
                    batch_size=self.batch_size, should_cancel=should_cancel):
                segments.append(segment)
                if on_progress:
                    on_progress(segment['end'], duration, segment)
            timings['asr_seconds'] = time.monotonic() - started
            diarize = options.get('diarize', False)
            phase('aligning')
            align_entry = self.manifest.get('aligners', {}).get(language)
            if profile and align_entry:
                expected_aligner = profile['models']['aligners'].get(language)
                if not expected_aligner or expected_aligner.get('revision') != align_entry['revision']:
                    raise WhisperXError('TRANSCRIPTION_PROFILE_MISMATCH', 'aligner revision')
            alignment = {'status': 'unavailable', 'model': None}
            if segments and not align_entry and diarize:
                raise WhisperXError('ALIGNMENT_UNSUPPORTED_LANGUAGE', language or 'unknown')
            if segments and align_entry:
                # Sequential stages release ASR weights before loading PyTorch.
                self.release()
                started = time.monotonic()
                align_path = Path(self._path(align_entry))
                if align_entry.get('backend') == 'torchaudio':
                    import torchaudio
                    bundle_name = align_entry['model']
                    bundle = getattr(torchaudio.pipelines, bundle_name)
                    if Path(bundle._path).name != align_path.name:
                        raise WhisperXError('DIARIZATION_MODEL_UNAVAILABLE', 'aligner filename mismatch')
                    aligner, meta = whisperx.load_align_model(language, self.device,
                        model_name=bundle_name, model_dir=str(align_path.parent), model_cache_only=True)
                else:
                    aligner, meta = whisperx.load_align_model(language, self.device,
                        model_name=str(align_path), model_cache_only=True)
                aligned = []
                try:
                    for segment in segments:
                        _check_cancel(should_cancel)
                        part = whisperx.align([segment], aligner, meta, audio, self.device,
                                              return_char_alignments=False)
                        aligned.extend(part['segments'])
                finally:
                    del aligner
                    gc.collect()
                segments = aligned
                alignment = {'status': 'completed', 'model': align_entry.get('model', align_entry['path']),
                             'revision': align_entry['revision'], 'device': self.device}
                timings['alignment_seconds'] = time.monotonic() - started
            elif not segments:
                alignment = {'status': 'completed', 'model': None}
            speakers, turns = [], []
            diarization = {'status': 'disabled', 'speaker_count': None, 'turns': []}
            if diarize:
                phase('diarizing')
                self.release()
                from whisperx.diarize import DiarizationPipeline
                entry = self.manifest.get('diarizer')
                if not entry:
                    raise WhisperXError('DIARIZATION_MODEL_UNAVAILABLE')
                started = time.monotonic()
                try:
                    pipeline = DiarizationPipeline(model_name=self._path(entry), device=self.device)
                    try:
                        frame = pipeline(audio, min_speakers=options.get('min_speakers'),
                                         max_speakers=options.get('max_speakers'))
                    finally:
                        del pipeline
                        gc.collect()
                except Exception as exc:
                    _check_cancel(should_cancel)
                    # GPU failures retain their type for the existing CPU retry guard.
                    if any(word in str(exc).lower() for word in ('cuda', 'cudnn', 'out of memory')):
                        raise
                    code = 'DIARIZATION_MODEL_UNAVAILABLE' if isinstance(exc, (FileNotFoundError, OSError)) or type(exc).__name__ in ('GatedRepoError', 'RepositoryNotFoundError') else 'DIARIZATION_FAILED'
                    raise WhisperXError(code, type(exc).__name__) from exc
                _check_cancel(should_cancel)
                rows = sorted(frame.to_dict('records'), key=lambda row: (row['start'], row['end'], str(row['speaker'])))
                labels = {}
                for row in rows:
                    source = str(row['speaker'])
                    if source not in labels:
                        if len(labels) >= 20:
                            raise WhisperXError('SPEAKER_LIMIT_EXCEEDED')
                        labels[source] = f'SPEAKER_{len(labels):02d}'
                    turns.append({'start': max(0., float(row['start'])), 'end': min(duration, float(row['end'])),
                                  'speaker_id': labels[source]})
                turns = [turn for turn in turns if turn['end'] > turn['start']]
                speakers = [{'id': sid, 'label': f'Falante {i+1}'} for i, sid in enumerate(labels.values())]
                diarization = {'status': 'completed', 'engine': 'pyannote', 'model': entry.get('model', entry['path']),
                               'revision': entry['revision'], 'speaker_count': len(speakers), 'turns': turns}
                timings['diarization_seconds'] = time.monotonic() - started
            text = ' '.join(segment['text'].strip() for segment in segments).strip()
            normalized = normalize_aligned_segments(segments, turns, expose_words=options.get('include_word_timestamps', False))
            phase('saving')
            return validate_result({'schema_version': 2, 'text': text, 'segments': normalized,
                'language': language, 'language_probability': None, 'duration': duration,
                'word_count': len(text.split()), 'char_count': len(text), 'provider': 'whisperx',
                'model': model_name, 'device': self.device, 'speakers': speakers, 'diarization': diarization,
                'alignment': alignment, 'provenance': {'whisperx': VERSION, 'models': self.manifest,
                    'device': self.device, 'compute_type': self.compute_type, 'timings': timings,
                    'beam_size': options.get('beam_size', 5), 'temperature': options.get('temperature', 0.0)}})


def transcribe(model, audio_path, options=None, *, model_name='turbo', on_progress=None, should_cancel=None):
    """Identical entry point to whisper_core, consumed by the Modal runner."""
    return model.transcribe(audio_path, options, model_name=model_name, on_progress=on_progress,
                            should_cancel=should_cancel)
