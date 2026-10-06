"""Production cannot reach unpatched model runtimes through options or cached models."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from workers.engines.runtime_security import RuntimeSecurityBlocked, require_safe_runtime


@pytest.mark.parametrize("environment", [None, "production", "staging", "", "PRODUCTION"])
@pytest.mark.parametrize("provider", ["whisperx", "diart"])
def test_only_explicit_development_can_qualify(provider, environment, monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    if environment is not None:
        monkeypatch.setenv("ENVIRONMENT", environment)
    with pytest.raises(RuntimeSecurityBlocked):
        require_safe_runtime(provider)


def test_local_qualification_requires_development(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    require_safe_runtime("whisperx")
    require_safe_runtime("diart")
    require_safe_runtime("faster-whisper", environment="production")


def test_persisted_profile_or_retry_override_cannot_reach_factory(monkeypatch):
    from shared import config
    from workers.audio import factory
    settings = SimpleNamespace(audio_transcriber_provider="faster-whisper", environment="production")
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    build = Mock()
    monkeypatch.setattr(factory, "_build_transcriber", build)
    with pytest.raises(RuntimeSecurityBlocked):
        # This is the same fallback entry used after durable profile options
        # are merged into retries by workers.tasks._transcribe_audio.
        factory.transcribe_with_gpu_fallback(__import__("pathlib").Path("/unused.wav"),
            options={"transcriber_provider": "whisperx"}, force_provider="whisperx")
    build.assert_not_called()


def test_whisperx_constructor_blocks_before_package_or_manifest_access(monkeypatch):
    from workers.engines import whisperx_core
    monkeypatch.setenv("ENVIRONMENT", "production")
    version = Mock(side_effect=AssertionError("must not import ML dependencies"))
    monkeypatch.setattr(whisperx_core.importlib.metadata, "version", version)
    with pytest.raises(RuntimeSecurityBlocked):
        whisperx_core.WhisperXRuntime("/nonexistent")
    version.assert_not_called()


def test_cached_remote_model_cannot_bypass_gate(monkeypatch):
    from workers.engines.whisperx_core import transcribe
    monkeypatch.setenv("ENVIRONMENT", "production")
    model = Mock()
    with pytest.raises(RuntimeSecurityBlocked):
        transcribe(model, "/tmp/unused.wav", {})
    model.transcribe.assert_not_called()


def test_diart_session_blocks_before_torch_import(monkeypatch):
    from workers.live.diart_process import DiartSession
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeSecurityBlocked):
        DiartSession({})


def test_remote_options_cannot_override_production_gate_even_from_development(monkeypatch):
    from workers.engines.modal_apps import protocol, runner
    monkeypatch.setenv("ENVIRONMENT", "development")
    request = protocol.build_request(attempt_key="release-gate", media=b"audio", suffix=".wav",
        options={"transcriber_provider": "whisperx"}, deadline_unix=2e9)
    inference = Mock()
    with pytest.raises(RuntimeSecurityBlocked):
        runner.handle(request, model=Mock(), state=None, container_id="unit", call_id=None,
            cold_start_seconds=0, gpu="L4", fingerprint="unit", transcribe=inference)
    inference.assert_not_called()


def test_remote_unsupported_provider_is_rejected():
    from workers.engines.modal_apps import protocol
    with pytest.raises(protocol.ProtocolError):
        protocol.build_request(attempt_key="unit", media=b"audio", suffix=".wav",
            options={"transcriber_provider": "unsupported"}, deadline_unix=2e9)
