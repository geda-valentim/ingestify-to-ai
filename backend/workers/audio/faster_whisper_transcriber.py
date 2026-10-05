"""
FasterWhisper transcription implementation

Uses faster-whisper library which is 4-5x faster than openai-whisper
while maintaining the same accuracy. Recommended for production use.

Repository: https://github.com/SYSTRAN/faster-whisper
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from workers.audio.base_transcriber import AudioTranscriber, ProgressCallback, VIDEO_FORMATS

logger = logging.getLogger(__name__)


class FasterWhisperTranscriber(AudioTranscriber):
    """
    Audio transcription using faster-whisper

    This implementation uses CTranslate2 for optimized inference,
    providing 4-5x speed improvement over the original OpenAI Whisper.
    """

    def __init__(
        self,
        model_size: str = "turbo",
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: str = None
    ):
        """
        Initialize FasterWhisper transcriber

        Args:
            model_size: Model size ('tiny', 'base', 'small', 'medium', 'large', 'turbo')
            device: Device to use ('cpu' or 'cuda')
            compute_type: Compute type ('int8', 'float16', 'float32')
            download_root: Directory to store downloaded models
        """
        try:
            import faster_whisper  # noqa: F401  (fail here with a clear message if missing)
        except ImportError as e:
            logger.error(
                "faster-whisper is not installed. "
                "Install it with: pip install faster-whisper"
            )
            raise ImportError(
                "faster-whisper library is required for FasterWhisperTranscriber"
            ) from e

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

        logger.info(
            f"Initializing FasterWhisper (model={model_size}, device={device}, "
            f"compute_type={compute_type})"
        )

        # Initialize model (with the bounded-memory spectrogram)
        from workers.engines import whisper_core
        self.model = whisper_core.load_model(model_size, device, compute_type, download_root)

        logger.info(f"FasterWhisper model '{model_size}' loaded successfully")

    def transcribe(
        self,
        audio_path: Path,
        options: Dict[str, Any] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """Transcribe audio file using faster-whisper"""
        if options is None:
            options = {}

        # Validate input
        self._validate_audio_file(audio_path)

        logger.info(f"Transcribing audio file: {audio_path}")

        try:
            from workers.engines import whisper_core
            result = whisper_core.transcribe(
                self.model, audio_path, options, model_name=self.model_size, on_progress=on_progress,
            )
            logger.info(
                f"Transcription complete: {result['word_count']} words, "
                f"{result['duration']:.2f}s duration, language={result['language']}"
            )

            return result

        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            raise Exception(f"Failed to transcribe audio: {str(e)}") from e

    def detect_language(self, audio_path: Path) -> str:
        """Detect language using faster-whisper"""
        self._validate_audio_file(audio_path)

        logger.info(f"Detecting language for: {audio_path}")

        try:
            # Transcribe only first 30 seconds for language detection
            segments, info = self.model.transcribe(
                str(audio_path),
                language=None,  # Auto-detect
                beam_size=5,
                vad_filter=True
            )

            # Consume first segment to trigger detection
            next(segments, None)

            language = info.language
            probability = info.language_probability

            logger.info(
                f"Detected language: {language} "
                f"(probability: {probability:.2f})"
            )

            return language

        except Exception as e:
            logger.error(f"Language detection failed: {e}", exc_info=True)
            raise Exception(f"Failed to detect language: {str(e)}") from e

    def get_audio_info(self, audio_path: Path) -> Dict[str, Any]:
        """Get audio metadata using pydub"""
        self._validate_audio_file(audio_path)

        try:
            from pydub import AudioSegment
            from pydub.utils import mediainfo
        except ImportError as e:
            logger.error("pydub is not installed. Install it with: pip install pydub")
            raise ImportError("pydub library is required for audio metadata extraction") from e

        try:
            # Load audio file
            audio = AudioSegment.from_file(str(audio_path))
            info = mediainfo(str(audio_path))

            # Extract metadata
            metadata = {
                'duration': len(audio) / 1000.0,  # Convert to seconds
                'format': audio_path.suffix.lower().lstrip('.'),
                'channels': audio.channels,
                'sample_rate': audio.frame_rate,
                'sample_width': audio.sample_width,
                'frame_count': audio.frame_count(),
                'frame_width': audio.frame_width,
                'size_bytes': audio_path.stat().st_size
            }

            # Add bitrate if available
            if 'bit_rate' in info:
                metadata['bitrate'] = int(info['bit_rate'])

            logger.info(
                f"Audio info: {metadata['duration']:.2f}s, "
                f"{metadata['format']}, {metadata['sample_rate']}Hz"
            )

            return metadata

        except Exception as e:
            logger.error(f"Failed to get audio info: {e}", exc_info=True)
            raise Exception(f"Failed to extract audio metadata: {str(e)}") from e

    def supported_formats(self) -> List[str]:
        """
        Get supported audio formats

        faster-whisper supports most common audio formats through ffmpeg
        """
        return [
            'mp3',
            'wav',
            'm4a',
            'flac',
            'ogg',
            'opus',
            'webm',
            'wma',
            'aac',
            'oga',
            'spx'
        ] + VIDEO_FORMATS
