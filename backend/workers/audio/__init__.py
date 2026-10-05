"""
Audio transcription module

Provides interface-based architecture for audio transcription with multiple provider support.

The factory (and with it shared.config) is imported on first use, not when the
package is: the Modal image of spec 0003 imports workers.audio.feature_extractor
through workers.engines.whisper_core and has no Ingestify settings to load.
"""

__all__ = ["get_audio_transcriber", "transcribe_with_gpu_fallback"]


def __getattr__(name):
    if name in __all__:
        from workers.audio import factory

        value = getattr(factory, name)
        globals()[name] = value  # later lookups (and monkeypatching) see a plain attribute
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
