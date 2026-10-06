"""Durable transcription decisions. No inference imports or credentials.

The provider default remains legacy until the qualification in spec 0006 passes.
Profiles are resolved once, before enqueue, and survive configuration changes.
"""
import hashlib
import json
from pathlib import Path

MEDIA_EXTENSIONS = frozenset('mp3 wav m4a flac ogg opus webm wma aac oga spx mp4 m4v mkv mov avi wmv flv mpeg mpg ts 3gp'.split())
WHISPERX_VERSION = '3.8.6'
MODEL_MANIFEST = {
    'asr': {'repo': 'mobiuslabsgmbh/faster-whisper-large-v3-turbo', 'revision': '0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf'},
    # These weights must be provisioned and their immutable revisions supplied by
    # the deployment manifest before readiness is enabled. No token in a profile.
    'diarizer': {'repo': 'pyannote/speaker-diarization-community-1'},
    'vad': {'method': 'silero', 'onset': 0.5, 'offset': 0.363},
}


def is_media_filename(filename):
    return Path(filename or '').suffix.lower().lstrip('.') in MEDIA_EXTENSIONS


def normalize_options(settings, options=None, *, known_media=None):
    options = dict(options or {})
    provider = options.get('transcriber_provider') or settings.audio_transcriber_provider
    explicit = options.get('diarize')
    options.setdefault('diarization_explicit', explicit is True or options.get('min_speakers') is not None or options.get('max_speakers') is not None)
    if explicit is not None and type(explicit) is not bool:
        raise ValueError('diarize must be a boolean')
    diarize = explicit if explicit is not None else (provider == 'whisperx' and settings.whisperx_diarization_default)
    if known_media is False and (explicit is True or options.get('min_speakers') is not None or options.get('max_speakers') is not None):
        raise ValueError('DIARIZATION_MEDIA_REQUIRED')
    if diarize and provider != 'whisperx':
        raise ValueError('DIARIZATION_UNSUPPORTED_PROVIDER')
    for key in ('min_speakers', 'max_speakers'):
        value = options.get(key)
        if value is not None and (type(value) is not int or not 1 <= value <= 20):
            raise ValueError(f'{key} must be an integer from 1 to 20')
        if value is not None and not diarize:
            raise ValueError(f'{key} requires diarize=true')
    if options.get('min_speakers') is not None and options.get('max_speakers') is not None and options['min_speakers'] > options['max_speakers']:
        raise ValueError('min_speakers must not exceed max_speakers')
    options.update(transcriber_provider=provider, diarize=diarize,
                   include_word_timestamps=options.get('include_word_timestamps', False),
                   beam_size=options.get('beam_size', 5), temperature=options.get('temperature', 0.0))
    return options


def make_profile(settings, options):
    options = normalize_options(settings, options)
    return {
        'schema': 2, 'provider': options['transcriber_provider'],
        'models': {'asr': settings.whisper_model, 'asr_revision': getattr(settings, 'whisperx_asr_revision', MODEL_MANIFEST['asr']['revision']),
                   'diarizer': getattr(settings, 'whisperx_diarization_model', MODEL_MANIFEST['diarizer']['repo']),
                   'diarizer_revision': getattr(settings, 'whisperx_diarization_revision', ''),
                   'aligners': json.loads(getattr(settings, 'whisperx_aligner_manifest', '{}'))},
        'pipeline_version': WHISPERX_VERSION if options['transcriber_provider'] == 'whisperx' else 'legacy',
        'language': options.get('audio_language') or options.get('language'),
        'beam_size': options['beam_size'], 'temperature': options['temperature'],
        'diarize': options['diarize'], 'min_speakers': options.get('min_speakers'),
        'max_speakers': options.get('max_speakers'),
        'include_word_timestamps': options['include_word_timestamps'],
        'vad': dict(MODEL_MANIFEST['vad'], revision=getattr(settings, 'whisperx_vad_revision', 'unqualified')),
    }


def profile_hash(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def options_from_profile(profile, options=None):
    result = dict(options or {})
    for key in ('language', 'beam_size', 'temperature', 'diarize', 'min_speakers', 'max_speakers', 'include_word_timestamps'):
        result[key] = profile[key]
    result['transcriber_provider'] = profile['provider']
    result['transcription_profile'] = profile
    return result
