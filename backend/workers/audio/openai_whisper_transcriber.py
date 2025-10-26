"""
OpenAI Whisper transcription implementation

Uses the original openai-whisper library. This is the baseline implementation,
but slower than faster-whisper. Use this as a fallback option.

Repository: https://github.com/openai/whisper
"""

from pathlib import Path
from typing import Dict, Any, List
import logging

from workers.audio.base_transcriber import AudioTranscriber

logger = logging.getLogger(__name__)


class OpenAIWhisperTranscriber(AudioTranscriber):
    """
    Audio transcription using OpenAI Whisper (original implementation)

    This is the reference implementation but slower than faster-whisper.
    Use faster-whisper for production when possible.
    """

    def __init__(
        self,
        model_size: str = "turbo",
        device: str = None,
        download_root: str = None
    ):
        """
        Initialize OpenAI Whisper transcriber

        Args:
            model_size: Model size ('tiny', 'base', 'small', 'medium', 'large', 'turbo')
            device: Device to use ('cpu', 'cuda', or None for auto-detect)
            download_root: Directory to store downloaded models
        """
        try:
            import whisper
            import torch
        except ImportError as e:
            logger.error(
                "openai-whisper is not installed. "
                "Install it with: pip install openai-whisper"
            )
            raise ImportError(
                "openai-whisper library is required for OpenAIWhisperTranscriber"
            ) from e

        self.model_size = model_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        logger.info(
            f"Initializing OpenAI Whisper (model={model_size}, device={self.device})"
        )

        # Load model
        self.model = whisper.load_model(
            model_size,
            device=self.device,
            download_root=download_root
        )

        logger.info(f"OpenAI Whisper model '{model_size}' loaded successfully")

    def transcribe(self, audio_path: Path, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Transcribe audio file using OpenAI Whisper"""
        if options is None:
            options = {}

        # Validate input
        self._validate_audio_file(audio_path)

        logger.info(f"Transcribing audio file: {audio_path}")

        # Extract options
        language = options.get('language')  # None = auto-detect
        include_word_timestamps = options.get('include_word_timestamps', False)
        temperature = options.get('temperature', 0.0)
        beam_size = options.get('beam_size', 5)

        try:
            # Transcribe audio
            result = self.model.transcribe(
                str(audio_path),
                language=language,
                word_timestamps=include_word_timestamps,
                temperature=temperature,
                beam_size=beam_size,
                verbose=False
            )

            # Extract full text
            full_text = result['text'].strip()

            # Format segments
            formatted_segments = []
            for segment in result.get('segments', []):
                segment_dict = {
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'].strip()
                }

                # Add word-level timestamps if available
                if include_word_timestamps and 'words' in segment:
                    segment_dict['words'] = [
                        {
                            'word': word['word'],
                            'start': word['start'],
                            'end': word['end'],
                            'probability': word.get('probability', 0.0)
                        }
                        for word in segment['words']
                    ]

                formatted_segments.append(segment_dict)

            # Calculate statistics
            word_count = len(full_text.split())
            char_count = len(full_text)

            # Get audio duration (calculate from last segment or use audio file)
            duration = 0.0
            if formatted_segments:
                duration = formatted_segments[-1]['end']

            # Get detected language
            detected_language = result.get('language', 'unknown')

            transcription_result = {
                'text': full_text,
                'segments': formatted_segments,
                'language': detected_language,
                'duration': duration,
                'word_count': word_count,
                'char_count': char_count,
                'model': self.model_size,
                'provider': 'openai-whisper'
            }

            logger.info(
                f"Transcription complete: {word_count} words, "
                f"{duration:.2f}s duration, language={detected_language}"
            )

            return transcription_result

        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            raise Exception(f"Failed to transcribe audio: {str(e)}") from e

    def detect_language(self, audio_path: Path) -> str:
        """Detect language using OpenAI Whisper"""
        self._validate_audio_file(audio_path)

        logger.info(f"Detecting language for: {audio_path}")

        try:
            import whisper

            # Load audio and detect language
            audio = whisper.load_audio(str(audio_path))

            # Pad or trim to 30 seconds for detection
            audio = whisper.pad_or_trim(audio)

            # Make log-Mel spectrogram
            mel = whisper.log_mel_spectrogram(audio).to(self.model.device)

            # Detect language
            _, probs = self.model.detect_language(mel)
            detected_language = max(probs, key=probs.get)

            logger.info(
                f"Detected language: {detected_language} "
                f"(probability: {probs[detected_language]:.2f})"
            )

            return detected_language

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

        OpenAI Whisper supports most common audio formats through ffmpeg
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
        ]
