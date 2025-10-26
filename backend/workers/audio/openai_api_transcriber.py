"""
OpenAI API transcription implementation

Uses OpenAI's cloud-based Whisper API for transcription.
This is the fastest option but requires API key and has costs.

Pricing: $0.006 per minute (as of 2025)
API Docs: https://platform.openai.com/docs/guides/speech-to-text
"""

from pathlib import Path
from typing import Dict, Any, List
import logging

from workers.audio.base_transcriber import AudioTranscriber

logger = logging.getLogger(__name__)


class OpenAIAPITranscriber(AudioTranscriber):
    """
    Audio transcription using OpenAI API

    Cloud-based transcription with fastest processing time.
    Requires OpenAI API key and incurs costs ($0.006/minute).
    """

    # OpenAI API file size limit (25MB)
    MAX_FILE_SIZE_MB = 25

    def __init__(self, api_key: str):
        """
        Initialize OpenAI API transcriber

        Args:
            api_key: OpenAI API key

        Raises:
            ValueError: If API key is not provided
            ImportError: If openai library is not installed
        """
        if not api_key:
            raise ValueError("OpenAI API key is required for OpenAIAPITranscriber")

        try:
            from openai import OpenAI
        except ImportError as e:
            logger.error(
                "openai library is not installed. "
                "Install it with: pip install openai"
            )
            raise ImportError(
                "openai library is required for OpenAIAPITranscriber"
            ) from e

        self.client = OpenAI(api_key=api_key)
        logger.info("Initialized OpenAI API transcriber")

    def transcribe(self, audio_path: Path, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Transcribe audio file using OpenAI API"""
        if options is None:
            options = {}

        # Validate input
        self._validate_audio_file(audio_path)
        self._validate_file_size(audio_path)

        logger.info(f"Transcribing audio file via OpenAI API: {audio_path}")

        # Extract options
        language = options.get('language')  # None = auto-detect
        include_word_timestamps = options.get('include_word_timestamps', False)
        temperature = options.get('temperature', 0.0)

        # Determine response format
        if include_word_timestamps:
            response_format = "verbose_json"
        else:
            response_format = "verbose_json"  # Always use verbose for metadata

        try:
            # Open and transcribe audio file
            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    temperature=temperature,
                    response_format=response_format,
                    timestamp_granularities=["segment", "word"] if include_word_timestamps else ["segment"]
                )

            # Parse response based on format
            if response_format == "verbose_json":
                full_text = transcript.text.strip()
                detected_language = getattr(transcript, 'language', 'unknown')
                duration = getattr(transcript, 'duration', 0.0)

                # Format segments
                formatted_segments = []
                if hasattr(transcript, 'segments'):
                    for segment in transcript.segments:
                        segment_dict = {
                            'start': segment.get('start', 0.0),
                            'end': segment.get('end', 0.0),
                            'text': segment.get('text', '').strip()
                        }

                        # Add word-level timestamps if available
                        if include_word_timestamps and 'words' in segment:
                            segment_dict['words'] = [
                                {
                                    'word': word.get('word', ''),
                                    'start': word.get('start', 0.0),
                                    'end': word.get('end', 0.0)
                                }
                                for word in segment.get('words', [])
                            ]

                        formatted_segments.append(segment_dict)

                # Calculate statistics
                word_count = len(full_text.split())
                char_count = len(full_text)

                result = {
                    'text': full_text,
                    'segments': formatted_segments,
                    'language': detected_language,
                    'duration': duration,
                    'word_count': word_count,
                    'char_count': char_count,
                    'model': 'whisper-1',
                    'provider': 'openai-api'
                }

                logger.info(
                    f"Transcription complete via API: {word_count} words, "
                    f"{duration:.2f}s duration, language={detected_language}"
                )

                return result

        except Exception as e:
            logger.error(f"API transcription failed: {e}", exc_info=True)
            raise Exception(f"Failed to transcribe audio via OpenAI API: {str(e)}") from e

    def detect_language(self, audio_path: Path) -> str:
        """
        Detect language using OpenAI API

        Note: The API doesn't have a dedicated language detection endpoint,
        so we perform a transcription and extract the language.
        """
        self._validate_audio_file(audio_path)
        self._validate_file_size(audio_path)

        logger.info(f"Detecting language via OpenAI API: {audio_path}")

        try:
            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json"
                )

            detected_language = getattr(transcript, 'language', 'unknown')

            logger.info(f"Detected language via API: {detected_language}")

            return detected_language

        except Exception as e:
            logger.error(f"Language detection failed: {e}", exc_info=True)
            raise Exception(f"Failed to detect language via API: {str(e)}") from e

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

            # Check if file exceeds API limit
            size_mb = metadata['size_bytes'] / (1024 * 1024)
            if size_mb > self.MAX_FILE_SIZE_MB:
                metadata['warning'] = (
                    f"File size ({size_mb:.2f}MB) exceeds OpenAI API limit "
                    f"({self.MAX_FILE_SIZE_MB}MB). File needs to be split or compressed."
                )

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
        Get supported audio formats for OpenAI API

        OpenAI API supports: mp3, mp4, mpeg, mpga, m4a, wav, webm
        """
        return [
            'mp3',
            'mp4',
            'mpeg',
            'mpga',
            'm4a',
            'wav',
            'webm'
        ]

    def _validate_file_size(self, audio_path: Path) -> None:
        """
        Validate that audio file doesn't exceed API limit

        Args:
            audio_path: Path to audio file

        Raises:
            ValueError: If file size exceeds 25MB limit
        """
        file_size_bytes = audio_path.stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)

        if file_size_mb > self.MAX_FILE_SIZE_MB:
            raise ValueError(
                f"Audio file size ({file_size_mb:.2f}MB) exceeds OpenAI API limit "
                f"of {self.MAX_FILE_SIZE_MB}MB. Please compress or split the file."
            )
