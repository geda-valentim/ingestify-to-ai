"""
The audio transcriber factory (spec 0003, slice 4a): a forced provider - one
job's `transcriber_provider` option - gets a throwaway instance and never
repoints the worker process's cached transcriber for every later job.
"""

import pytest

from workers.audio import factory


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    built = []

    def build(provider, settings):
        instance = object.__new__(type(f"Fake_{provider.replace('-', '_')}", (), {}))
        built.append(provider)
        return instance

    monkeypatch.setattr(factory, "_build_transcriber", build)
    monkeypatch.setattr(factory.get_settings() if hasattr(factory, "get_settings") else
                        __import__("shared.config", fromlist=["get_settings"]).get_settings(),
                        "audio_transcriber_provider", "faster-whisper")
    factory.reset_audio_transcriber()
    yield built
    factory.reset_audio_transcriber()


def test_a_forced_provider_does_not_replace_the_cached_transcriber(fresh):
    configured = factory.get_audio_transcriber()
    forced = factory.get_audio_transcriber(force_provider="openai-api")
    assert forced is not configured
    assert factory.get_audio_transcriber() is configured  # the next job still gets the configured one
    assert fresh == ["faster-whisper", "openai-api"]


def test_forcing_the_configured_provider_reuses_the_cached_instance(fresh):
    configured = factory.get_audio_transcriber()
    assert factory.get_audio_transcriber(force_provider="faster-whisper") is configured
    assert fresh == ["faster-whisper"]


def test_reset_rebuilds_the_configured_transcriber(fresh):
    first = factory.get_audio_transcriber()
    factory.reset_audio_transcriber()
    assert factory.get_audio_transcriber() is not first
