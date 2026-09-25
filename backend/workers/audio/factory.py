"""
Factory for audio transcriber instances

Provides singleton access to audio transcribers based on configuration.
This allows switching between different Whisper implementations via environment variables.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from workers.audio.base_transcriber import AudioTranscriber
from workers.audio.device import (
    WhisperDevice,
    get_whisper_device,
    is_gpu_error,
    mark_gpu_unavailable,
)

logger = logging.getLogger(__name__)

# Global singleton instance
_transcriber_instance: Optional[AudioTranscriber] = None


def get_audio_transcriber(force_provider: Optional[str] = None) -> AudioTranscriber:
    """
    Get or create audio transcriber instance (singleton pattern)

    The provider is determined by the AUDIO_TRANSCRIBER_PROVIDER environment variable.
    Supported providers:
    - faster-whisper (default, recommended): 4-5x faster than openai-whisper
    - openai-whisper: Original implementation, slower but reliable
    - openai-api: Cloud-based, fastest but requires API key and costs money

    Args:
        force_provider: Override the configured provider (optional)
                       Use this to temporarily switch providers without changing config

    Returns:
        AudioTranscriber instance

    Raises:
        ValueError: If provider is unknown or configuration is invalid
        ImportError: If required library for provider is not installed

    Example:
        >>> transcriber = get_audio_transcriber()
        >>> result = transcriber.transcribe(Path("audio.mp3"))

        >>> # Force specific provider
        >>> api_transcriber = get_audio_transcriber(force_provider="openai-api")
    """
    global _transcriber_instance

    # Get configuration
    from shared.config import get_settings
    settings = get_settings()

    # Determine which provider to use
    provider = force_provider or settings.audio_transcriber_provider

    # Return cached instance if provider hasn't changed
    if _transcriber_instance is not None and not force_provider:
        return _transcriber_instance

    logger.info(f"Initializing audio transcriber with provider: {provider}")

    # Create appropriate transcriber based on provider
    if provider == "faster-whisper":
        _transcriber_instance = _create_faster_whisper_transcriber(settings)

    elif provider == "openai-whisper":
        _transcriber_instance = _create_openai_whisper_transcriber(settings)

    elif provider == "openai-api":
        _transcriber_instance = _create_openai_api_transcriber(settings)

    else:
        raise ValueError(
            f"Unknown audio transcriber provider: {provider}. "
            f"Supported providers: faster-whisper, openai-whisper, openai-api"
        )

    logger.info(f"Audio transcriber initialized successfully with provider: {provider}")

    return _transcriber_instance


def _create_faster_whisper_transcriber(settings) -> AudioTranscriber:
    """Create FasterWhisper transcriber instance"""
    try:
        from workers.audio.faster_whisper_transcriber import FasterWhisperTranscriber
    except ImportError as e:
        logger.error(
            "faster-whisper is not installed. "
            "Install it with: pip install faster-whisper"
        )
        raise ImportError(
            "faster-whisper library is required. "
            "Run: pip install faster-whisper"
        ) from e

    return _create_on_best_device(
        lambda d: FasterWhisperTranscriber(
            model_size=settings.whisper_model,
            device=d.device,
            compute_type=d.compute_type
        )
    )


def _create_openai_whisper_transcriber(settings) -> AudioTranscriber:
    """Create OpenAI Whisper transcriber instance"""
    try:
        from workers.audio.openai_whisper_transcriber import OpenAIWhisperTranscriber
    except ImportError as e:
        logger.error(
            "openai-whisper is not installed. "
            "Install it with: pip install openai-whisper"
        )
        raise ImportError(
            "openai-whisper library is required. "
            "Run: pip install openai-whisper"
        ) from e

    return _create_on_best_device(
        lambda d: OpenAIWhisperTranscriber(
            model_size=settings.whisper_model,
            device=d.device
        )
    )


def _create_openai_api_transcriber(settings) -> AudioTranscriber:
    """Create OpenAI API transcriber instance"""
    try:
        from workers.audio.openai_api_transcriber import OpenAIAPITranscriber
    except ImportError as e:
        logger.error(
            "openai library is not installed. "
            "Install it with: pip install openai"
        )
        raise ImportError(
            "openai library is required. "
            "Run: pip install openai"
        ) from e

    # Validate API key
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is required for openai-api provider"
        )

    return OpenAIAPITranscriber(api_key=settings.openai_api_key)


def _create_on_best_device(create: Callable[[WhisperDevice], AudioTranscriber]) -> AudioTranscriber:
    """
    Build a local Whisper transcriber on the cached device (GPU when available).

    If the model cannot be loaded on the GPU because of a GPU/CUDA error, the GPU is
    marked unavailable for this worker process and the model is loaded on CPU instead.
    """
    device = get_whisper_device()
    try:
        return create(device)
    except Exception as e:
        # Only GPU problems disable the GPU; e.g. a model download error must not
        if device.device != "cuda" or not is_gpu_error(e):
            raise
        logger.error(f"Failed to load Whisper on GPU, falling back to CPU: {e}")
        return create(mark_gpu_unavailable(str(e)))


def transcribe_with_gpu_fallback(
    audio_path: Path,
    options: Optional[Dict[str, Any]] = None,
    force_provider: Optional[str] = None,
) -> Tuple[Dict[str, Any], AudioTranscriber]:
    """
    Transcribe with the configured transcriber, retrying once on CPU if the GPU fails.

    Some CUDA problems (e.g. cuDNN libraries missing) only surface when the model
    runs, not when it loads. In that case the GPU is marked unavailable for this
    worker process, the transcriber is rebuilt on CPU and the job is retried.
    """
    transcriber = get_audio_transcriber(force_provider=force_provider)
    try:
        result = transcriber.transcribe(audio_path, options)
    except Exception as e:
        if getattr(transcriber, "device", None) != "cuda" or not is_gpu_error(e):
            raise
        logger.error(f"Transcription failed on GPU, retrying on CPU: {e}")
        mark_gpu_unavailable(str(e))
        reset_audio_transcriber()
        transcriber = get_audio_transcriber(force_provider=force_provider)
        result = transcriber.transcribe(audio_path, options)

    result.setdefault("device", getattr(transcriber, "device", None) or "remote")
    return result, transcriber


def reset_audio_transcriber() -> None:
    """
    Reset the singleton instance

    Useful for testing or when you want to reload the transcriber
    with different configuration.
    """
    global _transcriber_instance
    _transcriber_instance = None
    logger.info("Audio transcriber instance reset")


def get_available_providers() -> dict[str, dict]:
    """
    Get information about available transcriber providers

    Returns:
        Dictionary with provider information:
        {
            "faster-whisper": {
                "available": True/False,
                "description": "...",
                "speed": "4-5x faster",
                "cost": "Free (local)"
            },
            ...
        }
    """
    providers = {}

    # Check faster-whisper
    try:
        import faster_whisper
        providers["faster-whisper"] = {
            "available": True,
            "description": "Optimized Whisper using CTranslate2",
            "speed": "4-5x faster than openai-whisper",
            "cost": "Free (local processing)",
            "recommended": True
        }
    except ImportError:
        providers["faster-whisper"] = {
            "available": False,
            "description": "Not installed. Run: pip install faster-whisper",
            "recommended": True
        }

    # Check openai-whisper
    try:
        import whisper
        providers["openai-whisper"] = {
            "available": True,
            "description": "Original OpenAI Whisper implementation",
            "speed": "Baseline speed",
            "cost": "Free (local processing)",
            "recommended": False
        }
    except ImportError:
        providers["openai-whisper"] = {
            "available": False,
            "description": "Not installed. Run: pip install openai-whisper"
        }

    # Check openai API
    try:
        import openai
        from shared.config import get_settings
        settings = get_settings()

        has_api_key = bool(settings.openai_api_key)

        providers["openai-api"] = {
            "available": has_api_key,
            "description": "Cloud-based OpenAI Whisper API",
            "speed": "Fastest (cloud processing)",
            "cost": "$0.006 per minute",
            "requires_api_key": True,
            "api_key_configured": has_api_key,
            "recommended": False
        }
    except ImportError:
        providers["openai-api"] = {
            "available": False,
            "description": "Not installed. Run: pip install openai",
            "requires_api_key": True
        }

    return providers
