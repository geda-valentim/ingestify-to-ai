"""Compatibility imports for audio workers; contracts live in shared."""
from shared.audio_decoding import (
    FASTER_WHISPER_OPTIONS,
    OPENAI_API_OPTIONS,
    OPENAI_WHISPER_OPTIONS,
    PROVIDER_OPTIONS,
    clean_remote_options,
    decoding_kwargs,
)

__all__ = [
    "FASTER_WHISPER_OPTIONS", "OPENAI_API_OPTIONS", "OPENAI_WHISPER_OPTIONS",
    "PROVIDER_OPTIONS", "clean_remote_options", "decoding_kwargs",
]
