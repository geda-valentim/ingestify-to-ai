"""Local adapter for the common WhisperX runtime (spec 0006)."""
from pathlib import Path
from workers.audio.base_transcriber import AudioTranscriber
from workers.engines.whisperx_core import WhisperXRuntime


class WhisperXTranscriber(AudioTranscriber):
    def __init__(self, *, model_dir, model_size='turbo', device='cpu', compute_type='int8',
                 batch_size=1, max_audio_seconds=7200):
        self.model_size, self.device, self.compute_type = model_size, device, compute_type
        self.runtime = WhisperXRuntime(model_dir, device, compute_type, batch_size=batch_size,
                                       max_audio_seconds=max_audio_seconds)

    def transcribe(self, audio_path, options=None, on_progress=None):
        self._validate_audio_file(audio_path)
        return self.runtime.transcribe(audio_path, options, on_progress=on_progress, model_name=self.model_size)

    def detect_language(self, audio_path):
        self._validate_audio_file(audio_path)
        import whisperx
        with self.runtime.lock:
            return self.runtime._load_asr().detect_language(whisperx.load_audio(str(audio_path))[:30 * 16000])

    def get_audio_info(self, audio_path):
        self._validate_audio_file(audio_path)
        from pydub.utils import mediainfo
        info = mediainfo(str(audio_path))
        return {'duration': float(info['duration']), 'format': Path(audio_path).suffix.lstrip('.'),
                'channels': int(info['channels']), 'sample_rate': int(info['sample_rate']),
                'size_bytes': Path(audio_path).stat().st_size}

    def supported_formats(self):
        from shared.transcription import MEDIA_EXTENSIONS
        return sorted(MEDIA_EXTENSIONS)

    def release(self):
        self.runtime.release()
