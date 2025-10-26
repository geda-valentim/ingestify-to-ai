"""
Audio transcription module

Provides interface-based architecture for audio transcription with multiple provider support.
"""

from workers.audio.factory import get_audio_transcriber

__all__ = ["get_audio_transcriber"]
