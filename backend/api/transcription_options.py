"""Normalize multipart transcription inputs before writing or enqueueing a job."""
from fastapi import HTTPException
from fastapi.params import Param, Body

from shared.transcription import is_media_filename, make_profile, normalize_options, profile_hash

_DOCUMENT_EXTENSIONS = frozenset('.pdf .doc .docx .ppt .pptx .xls .xlsx .html .htm .txt .md .csv .rtf .odt .ods .odp .jpg .jpeg .png .tiff .bmp'.split())


def media_input_kind(filename, mime_type=None):
    """True for media, False for known documents, None if decoding must decide."""
    from pathlib import Path
    mime = (mime_type or '').split(';', 1)[0].lower()
    if is_media_filename(filename) or mime.startswith(('audio/', 'video/')):
        return True
    if Path(filename or '').suffix.lower() in _DOCUMENT_EXTENSIONS:
        return False
    return None


def admission(settings, *, known_media, base_options=None, language=None,
              diarize=None, min_speakers=None, max_speakers=None,
              include_word_timestamps=None):
    """Return (effective task options, durable candidate profile, hash).

    Unknown downloaded sources retain the decision made at enqueue. A document
    request never requires an available diarization model merely due to defaults.
    """
    inputs = dict(base_options or {})
    for key, value in {'language': language, 'diarize': diarize,
                       'min_speakers': min_speakers, 'max_speakers': max_speakers,
                       'include_word_timestamps': include_word_timestamps}.items():
        # Direct Python callers in existing tests do not resolve FastAPI defaults.
        if value is not None and not isinstance(value, (Param, Body)):
            inputs[key] = value
    try:
        effective = normalize_options(settings, inputs, known_media=known_media)
        if known_media is False:
            return dict(base_options or {}), None, None
        if effective['diarize'] and (known_media is True or inputs.get('diarize') is True):
            if not getattr(settings, 'whisperx_diarization_ready', False):
                raise HTTPException(503, detail={'code': 'DIARIZATION_NOT_READY'})
        profile = make_profile(settings, effective)
    except ValueError as exc:
        raise HTTPException(422, detail={'code': 'INVALID_TRANSCRIPTION_OPTIONS', 'message': str(exc)}) from None
    effective['transcription_profile'] = profile
    return effective, profile, profile_hash(profile)
