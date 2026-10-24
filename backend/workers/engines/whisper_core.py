"""
The Whisper decoding loop, shared by every engine that runs faster-whisper.

The local transcriber (workers.audio.faster_whisper_transcriber) and the Modal
app of spec 0003 both call this, so a lesson transcribed locally or remotely
gives the same result. Depends only on faster-whisper, numpy and
workers.audio.feature_extractor - nothing that needs Ingestify's settings, so
it runs inside a remote container as is.
"""

import gc
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# on_progress(transcribed_seconds, total_seconds, segment=None); see base_transcriber
ProgressCallback = Callable[..., None]


# Mirrors Settings.max_audio_duration_seconds; callers with settings pass theirs
DEFAULT_MAX_AUDIO_SECONDS = 3600
SAMPLE_RATE = 16000
# Container rounding and codec priming may add a little to a file that is exactly at the limit
DURATION_TOLERANCE_SECONDS = 1.0


class TranscriptionCancelled(Exception):
    """should_cancel() asked to stop between segments"""


class AudioDurationExceeded(ValueError):
    """The decoded audio is longer than the limit (the container's own duration is never trusted)"""

    code = "AUDIO_DURATION_LIMIT_EXCEEDED"

    def __init__(self, maximum_seconds: float):
        self.maximum_seconds = maximum_seconds
        super().__init__(f"{self.code}: audio is longer than {maximum_seconds:g}s")


def load_bounded_audio(path, maximum_seconds: float = DEFAULT_MAX_AUDIO_SECONDS):
    """
    Decode a media file to 16 kHz mono float32, like faster_whisper.audio.decode_audio
    but counting the samples as they come out of the decoder. Raises
    AudioDurationExceeded as soon as they pass maximum_seconds, before the rest of
    the file is decoded, so a small file that expands to hours (a FLAC of silence,
    metadata that lies about its length) cannot exhaust the worker's memory.
    """
    import av
    import numpy as np

    limit = int((maximum_seconds + DURATION_TOLERANCE_SECONDS) * SAMPLE_RATE)
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks, total = [], 0

    def take(frames):
        nonlocal total
        for frame in frames:
            array = frame.to_ndarray().reshape(-1)
            total += array.shape[0]
            if total > limit:
                raise AudioDurationExceeded(maximum_seconds)
            chunks.append(array)

    try:
        with av.open(str(path), mode="r", metadata_errors="ignore") as container:
            frames = iter(container.decode(audio=0))
            while True:
                try:
                    frame = next(frames)
                except StopIteration:
                    break
                except av.error.InvalidDataError:
                    continue  # as faster-whisper does: a corrupt frame is skipped
                take(resampler.resample(frame))
            take(resampler.resample(None))  # flush
    finally:
        del resampler
        gc.collect()  # PyAV resampler objects are not freed otherwise (faster-whisper#390)

    if not chunks:
        return np.zeros(0, dtype=np.float32)
    # s16 back to f32, as faster-whisper does
    return np.concatenate(chunks).astype(np.float32) / 32768.0


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
    max_audio_seconds: float = DEFAULT_MAX_AUDIO_SECONDS,
) -> Dict[str, Any]:
    """
    Transcribe one file with a loaded model.

    Returns the dict AudioTranscriber.transcribe() documents (text, segments,
    language, language_probability, duration, word_count, char_count, model,
    provider). should_cancel is checked after each decoded segment - the only
    point where Python regains control from CTranslate2 - and raises
    TranscriptionCancelled, so a remote call past its deadline stops spending.
    Audio longer than max_audio_seconds raises AudioDurationExceeded while decoding.
    """
    language = options.get('language')  # None = auto-detect
    include_word_timestamps = options.get('include_word_timestamps', False)
    temperature = options.get('temperature', 0.0)
    beam_size = options.get('beam_size', 5)

    audio = load_bounded_audio(audio_path, max_audio_seconds)

    segments, info = model.transcribe(
        audio,
        language=language,
        word_timestamps=include_word_timestamps,
        temperature=temperature,
        beam_size=beam_size,
        vad_filter=True,  # Voice activity detection filter
        vad_parameters=dict(min_silence_duration_ms=500)
    )

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

    return {
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
