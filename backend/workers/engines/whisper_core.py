"""
The Whisper decoding loop, shared by every engine that runs faster-whisper.

The local transcriber (workers.audio.faster_whisper_transcriber) and the Modal
app of spec 0003 both call this, so a lesson transcribed locally or remotely
gives the same result. Depends only on faster-whisper, numpy and
workers.audio.feature_extractor - nothing that needs Ingestify's settings, so
it runs inside a remote container as is.
"""

from pathlib import Path
from typing import Any, Callable, Dict, Optional
from workers.audio.decoding_options import decoding_kwargs

# on_progress(transcribed_seconds, total_seconds, segment=None); see base_transcriber
ProgressCallback = Callable[..., None]


class TranscriptionCancelled(Exception):
    """should_cancel() asked to stop between segments"""


def load_model(model_size: str, device: str, compute_type: str, download_root: Optional[str] = None):
    """A faster-whisper model with the bounded-memory spectrogram installed"""
    from faster_whisper import WhisperModel

    from workers.audio.feature_extractor import install

    model = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=download_root)
    # Bounded-memory spectrogram; the stock one grows with the audio length
    install(model)
    return model


def transcribe(
    model,
    audio_path: Path,
    options: Dict[str, Any],
    *,
    model_name: str,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """
    Transcribe one file with a loaded model.

    Returns the dict AudioTranscriber.transcribe() documents (text, segments,
    language, language_probability, duration, word_count, char_count, model,
    provider). should_cancel is checked after each decoded segment - the only
    point where Python regains control from CTranslate2 - and raises
    TranscriptionCancelled, so a remote call past its deadline stops spending.
    """
    include_word_timestamps = options.get('include_word_timestamps', False)
    operation = options.get('operation', 'transcribe')
    if operation == 'inspect':
        from workers.audio.analysis import media_info, analysis_result
        return analysis_result(operation=operation, info=media_info(audio_path), model=model_name, provider='faster-whisper')
    segments, info = model.transcribe(str(audio_path), **decoding_kwargs(options, 'faster-whisper'))
    if operation == 'detect_language':
        from workers.audio.analysis import analysis_result
        result = analysis_result(operation=operation, info={'duration': info.duration}, language=info.language,
                                 probability=info.language_probability, model=model_name, provider='faster-whisper')
        if getattr(info, 'all_language_probs', None):
            result['language_probabilities'] = dict(info.all_language_probs)
        return result

    # Segments are decoded lazily as the generator is consumed; each one's
    # end time (in the original audio, even with VAD) measures progress
    if on_progress:
        on_progress(0.0, info.duration)
    segments_list = []
    for segment in segments:
        segments_list.append(segment)
        if on_progress:
            on_progress(
                segment.end,
                info.duration,
                segment={"start": segment.start, "end": segment.end, "text": segment.text.strip()},
            )
        if should_cancel and should_cancel():
            raise TranscriptionCancelled(f"cancelled at {segment.end:.1f}s of {info.duration:.1f}s")

    # Build result
    full_text = ' '.join([segment.text.strip() for segment in segments_list])

    # Format segments
    formatted_segments = []
    for segment in segments_list:
        segment_dict = {
            'start': segment.start,
            'end': segment.end,
            'text': segment.text.strip()
        }
        for key in ('id', 'seek', 'tokens', 'temperature', 'avg_logprob', 'compression_ratio', 'no_speech_prob'):
            value = getattr(segment, key, None)
            if value is not None:
                segment_dict[key] = value

        # Add word-level timestamps if requested
        if include_word_timestamps and hasattr(segment, 'words') and segment.words:
            segment_dict['words'] = [
                {
                    'word': word.word,
                    'start': word.start,
                    'end': word.end,
                    'probability': word.probability
                }
                for word in segment.words
            ]

        formatted_segments.append(segment_dict)

    result = {
        'text': full_text,
        'segments': formatted_segments,
        'language': info.language,
        'language_probability': info.language_probability,
        'duration': info.duration,
        'word_count': len(full_text.split()),
        'char_count': len(full_text),
        'model': model_name,
        'provider': 'faster-whisper'
    }
    if getattr(info, 'all_language_probs', None):
        result['language_probabilities'] = dict(info.all_language_probs)
    if getattr(info, 'duration_after_vad', None) is not None:
        result['duration_after_vad'] = info.duration_after_vad
    return result
