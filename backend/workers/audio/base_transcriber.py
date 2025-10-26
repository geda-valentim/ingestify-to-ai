"""
Abstract base class for audio transcription

This module defines the interface that all audio transcription providers must implement.
This allows easy switching between different Whisper implementations (faster-whisper,
openai-whisper, OpenAI API) or future transcription services.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class AudioTranscriber(ABC):
    """
    Abstract base class for audio transcription

    All audio transcription providers must implement this interface.
    This ensures consistent behavior across different implementations.
    """

    @abstractmethod
    def transcribe(self, audio_path: Path, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Transcribe audio file to text

        Args:
            audio_path: Path to audio file
            options: Transcription options:
                - language (str, optional): Language code (e.g., 'en', 'pt'). Auto-detect if None.
                - include_timestamps (bool): Include timestamp markers in output (default: True)
                - include_word_timestamps (bool): Include word-level timestamps (default: False)
                - temperature (float): Sampling temperature (default: 0.0)
                - beam_size (int): Beam size for beam search (default: 5)

        Returns:
            Dictionary with transcription results:
            {
                "text": "Full transcription text",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.5,
                        "text": "Segment text",
                        "words": [  # Only if include_word_timestamps=True
                            {"word": "Hello", "start": 0.0, "end": 0.5},
                            ...
                        ]
                    },
                    ...
                ],
                "language": "en",
                "duration": 120.5,
                "word_count": 450,
                "char_count": 2500
            }

        Raises:
            FileNotFoundError: If audio file doesn't exist
            ValueError: If audio format is not supported
            Exception: If transcription fails
        """
        pass

    @abstractmethod
    def detect_language(self, audio_path: Path) -> str:
        """
        Detect the language of the audio file

        Args:
            audio_path: Path to audio file

        Returns:
            ISO 639-1 language code (e.g., 'en', 'pt', 'es')

        Raises:
            FileNotFoundError: If audio file doesn't exist
            Exception: If language detection fails
        """
        pass

    @abstractmethod
    def get_audio_info(self, audio_path: Path) -> Dict[str, Any]:
        """
        Get audio file metadata

        Args:
            audio_path: Path to audio file

        Returns:
            Dictionary with audio metadata:
            {
                "duration": 120.5,  # seconds
                "format": "mp3",
                "channels": 2,
                "sample_rate": 44100,
                "bitrate": 320000,
                "size_bytes": 5242880
            }

        Raises:
            FileNotFoundError: If audio file doesn't exist
            Exception: If metadata extraction fails
        """
        pass

    @abstractmethod
    def supported_formats(self) -> List[str]:
        """
        Get list of supported audio formats

        Returns:
            List of supported file extensions (e.g., ['mp3', 'wav', 'm4a', 'flac'])
        """
        pass

    def format_as_markdown(self, transcription: Dict[str, Any], include_timestamps: bool = True) -> str:
        """
        Format transcription result as markdown

        This is a concrete method (not abstract) providing default markdown formatting.
        Subclasses can override if they need custom formatting.

        Args:
            transcription: Transcription result from transcribe()
            include_timestamps: Whether to include timestamp markers

        Returns:
            Markdown-formatted transcription
        """
        lines = []

        # Add metadata header
        lines.append(f"# Audio Transcription\n")
        lines.append(f"**Language:** {transcription.get('language', 'unknown')}")
        lines.append(f"**Duration:** {transcription.get('duration', 0):.2f}s")
        lines.append(f"**Word Count:** {transcription.get('word_count', 0)}")
        lines.append(f"\n---\n")

        # Add transcription with timestamps
        if include_timestamps and 'segments' in transcription:
            for segment in transcription['segments']:
                start = segment.get('start', 0)
                minutes = int(start // 60)
                seconds = int(start % 60)
                timestamp = f"[{minutes:02d}:{seconds:02d}]"

                text = segment.get('text', '').strip()
                lines.append(f"{timestamp} {text}")
        else:
            # Just the full text without timestamps
            lines.append(transcription.get('text', ''))

        return '\n'.join(lines)

    def _validate_audio_file(self, audio_path: Path) -> None:
        """
        Validate that audio file exists and has supported format

        Args:
            audio_path: Path to audio file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If format is not supported
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        extension = audio_path.suffix.lower().lstrip('.')
        if extension not in self.supported_formats():
            raise ValueError(
                f"Unsupported audio format: {extension}. "
                f"Supported formats: {', '.join(self.supported_formats())}"
            )
