"""
Factory for audio transcriber instances

Provides singleton access to audio transcribers based on configuration.
This allows switching between different Whisper implementations via environment variables.

A forced provider (`force_provider`, e.g. one job's `transcriber_provider`
option) that differs from the configured one gets a throwaway instance and never
replaces the cached one: one request must not repoint the worker process for
every later job (spec 0003, slice 4a - the same rule as workers/vision/factory.py).
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from workers.audio.base_transcriber import AudioTranscriber, ProgressCallback
from workers.audio.device import (
    WhisperDevice,
    get_whisper_device,
    is_gpu_error,
    mark_gpu_unavailable,
)

logger = logging.getLogger(__name__)

# Global singleton instance, and the provider it was built for
_transcriber_instance: Optional[AudioTranscriber] = None
_transcriber_provider: Optional[str] = None


def get_audio_transcriber(force_provider: Optional[str] = None) -> AudioTranscriber:
    """
    Get or create audio transcriber instance (singleton pattern)

    The provider is determined by the AUDIO_TRANSCRIBER_PROVIDER environment variable.
    Supported providers:
    - faster-whisper (default, recommended): 4-5x faster than openai-whisper
    - openai-whisper: Original implementation, slower but reliable
    - openai-api: Cloud-based, fastest but requires API key and costs money

    Args:
        force_provider: Override the configured provider for this call only. A
                       provider other than the configured one is built as a throwaway
                       instance; the cached (configured) one is left alone.

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
    global _transcriber_instance, _transcriber_provider

    # Get configuration
    from shared.config import get_settings
    settings = get_settings()

    configured = settings.audio_transcriber_provider
    provider = force_provider or configured
    from workers.engines.runtime_security import require_safe_runtime
    require_safe_runtime(provider, environment=settings.environment)

    if provider != configured:
        logger.info(f"Building a one-off audio transcriber with provider: {provider}")
        return _build_transcriber(provider, settings)

    # Return the cached instance while it is the configured provider's
    if _transcriber_instance is not None and _transcriber_provider == provider:
        return _transcriber_instance

    logger.info(f"Initializing audio transcriber with provider: {provider}")
    _transcriber_instance = _build_transcriber(provider, settings)
    _transcriber_provider = provider
    logger.info(f"Audio transcriber initialized successfully with provider: {provider}")
    return _transcriber_instance


def _build_transcriber(provider: str, settings) -> AudioTranscriber:
    from workers.engines.runtime_security import require_safe_runtime
    require_safe_runtime(provider, environment=settings.environment)
    if provider == "whisperx":
        from workers.audio.whisperx_transcriber import WhisperXTranscriber
        return _create_on_best_device(lambda d: WhisperXTranscriber(
            model_dir=settings.whisperx_model_dir, model_size=settings.whisper_model,
            device=d.device, compute_type=d.compute_type, batch_size=settings.whisperx_batch_size,
            max_audio_seconds=settings.whisperx_max_audio_seconds))
    if provider == "faster-whisper":
        return _create_faster_whisper_transcriber(settings)
    if provider == "openai-whisper":
        return _create_openai_whisper_transcriber(settings)
    if provider == "openai-api":
        return _create_openai_api_transcriber(settings)
    raise ValueError(
        f"Unknown audio transcriber provider: {provider}. "
        f"Supported providers: whisperx, faster-whisper, openai-whisper, openai-api"
    )


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
        if not device.device.startswith("cuda") or not is_gpu_error(e):
            raise
        logger.error(f"Failed to load Whisper on GPU, falling back to CPU: {e}")
        return create(mark_gpu_unavailable(str(e)))


def transcribe_with_gpu_fallback(
    audio_path: Path,
    options: Optional[Dict[str, Any]] = None,
    force_provider: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Tuple[Dict[str, Any], AudioTranscriber]:
    """
    Transcribe with the configured transcriber, retrying once on CPU if the GPU fails.

    Some CUDA problems (e.g. cuDNN libraries missing) only surface when the model
    runs, not when it loads. In that case the GPU is marked unavailable for this
    worker process, the transcriber is rebuilt on CPU and the job is retried.
    """
    # Only passed when asked for, so a transcriber on the older two-argument interface still works
    progress_kwargs = {"on_progress": on_progress} if on_progress else {}
    transcriber = get_audio_transcriber(force_provider=force_provider)
    try:
        result = transcriber.transcribe(audio_path, options, **progress_kwargs)
    except Exception as e:
        if not str(getattr(transcriber, "device", "")).startswith("cuda") or not is_gpu_error(e):
            raise
        logger.error(f"Transcription failed on GPU, retrying on CPU: {e}")
        mark_gpu_unavailable(str(e))
        if hasattr(transcriber, "release"):
            transcriber.release()
        reset_audio_transcriber()
        if options and options.get('_reset_progress'):
            options['_reset_progress']()
        transcriber = get_audio_transcriber(force_provider=force_provider)
        result = transcriber.transcribe(audio_path, options, **progress_kwargs)

    result.setdefault("device", getattr(transcriber, "device", None) or "remote")
    return result, transcriber


def reset_audio_transcriber() -> None:
    """
    Reset the singleton instance

    Useful for testing or when you want to reload the transcriber
    with different configuration.
    """
    global _transcriber_instance, _transcriber_provider
    _transcriber_instance = None
    _transcriber_provider = None
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
    from importlib.util import find_spec
    providers['whisperx'] = {
        'available': find_spec('whisperx') is not None,
        'description': 'WhisperX alignment and speaker diarization (qualified canary)',
        'recommended': False,
    }

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
