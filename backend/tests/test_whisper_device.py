"""Whisper GPU detection: detected once per worker process, with a permanent CPU fallback."""
from pathlib import Path

import pytest

from workers.audio import device as device_module
from workers.audio import factory


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    device_module.reset_whisper_device()
    factory.reset_audio_transcriber()
    yield
    device_module.reset_whisper_device()
    factory.reset_audio_transcriber()


@pytest.fixture
def config(monkeypatch):
    from shared.config import get_settings
    settings = get_settings()

    def set_config(device="auto", compute_type="auto"):
        monkeypatch.setattr(settings, "whisper_device", device)
        monkeypatch.setattr(settings, "whisper_compute_type", compute_type)
    set_config()
    return set_config


@pytest.fixture
def gpus(monkeypatch):
    calls = []

    def set_count(count):
        def fake_count():
            calls.append(1)
            return count
        monkeypatch.setattr(device_module, "_cuda_device_count", fake_count)
    set_count(0)
    return set_count, calls


def test_auto_uses_gpu_when_available(config, gpus):
    set_count, _ = gpus
    set_count(1)
    selected = device_module.get_whisper_device()
    assert (selected.device, selected.compute_type) == ("cuda", "float16")


def test_auto_uses_cpu_without_gpu(config, gpus):
    selected = device_module.get_whisper_device()
    assert (selected.device, selected.compute_type) == ("cpu", "int8")


def test_detection_runs_only_once(config, gpus):
    set_count, calls = gpus
    set_count(1)
    for _ in range(5):
        device_module.get_whisper_device()
    assert len(calls) == 1


def test_forced_device_skips_detection(config, gpus):
    _, calls = gpus
    config(device="cpu")
    assert device_module.get_whisper_device().device == "cpu"
    assert calls == []


def test_explicit_compute_type_is_respected(config, gpus):
    set_count, _ = gpus
    set_count(1)
    config(compute_type="int8_float16")
    assert device_module.get_whisper_device().compute_type == "int8_float16"


def test_gpu_failure_switches_to_cpu_for_good(config, gpus):
    set_count, calls = gpus
    set_count(1)
    assert device_module.get_whisper_device().device == "cuda"

    device_module.mark_gpu_unavailable("libcudnn_ops.so.9 not found")

    for _ in range(3):
        selected = device_module.get_whisper_device()
        assert (selected.device, selected.compute_type) == ("cpu", "int8")
    assert len(calls) == 1  # no new detection after the fallback


@pytest.mark.parametrize(
    "error, expected",
    [
        (RuntimeError("CUDA failed with error out of memory"), True),
        (RuntimeError("Unable to load any of {libcudnn_ops.so.9}"), True),
        (RuntimeError("cuBLAS failed with status CUBLAS_STATUS_NOT_SUPPORTED"), True),
        (ValueError("Unsupported audio format: txt"), False),
    ],
)
def test_is_gpu_error(error, expected):
    assert device_module.is_gpu_error(error) is expected


class _FakeTranscriber:
    instances = []

    def __init__(self, device, fail_on=None):
        self.device = device
        self.fail_on = fail_on
        _FakeTranscriber.instances.append(self)

    def transcribe(self, path, options=None):
        if self.fail_on == self.device:
            raise RuntimeError("Unable to load any of {libcudnn_ops.so.9}")
        return {"text": "ok"}


def test_model_load_failure_on_gpu_falls_back_to_cpu(config, gpus):
    set_count, _ = gpus
    set_count(1)

    def create(selected):
        if selected.device == "cuda":
            raise RuntimeError("CUDA driver version is insufficient")
        return _FakeTranscriber(selected.device)

    transcriber = factory._create_on_best_device(create)
    assert transcriber.device == "cpu"
    assert device_module.get_whisper_device().device == "cpu"


def test_non_gpu_load_failure_keeps_gpu(config, gpus):
    set_count, _ = gpus
    set_count(1)

    def create(selected):
        raise OSError("Invalid model size 'huge', expected one of: tiny, base, small")

    with pytest.raises(OSError):
        factory._create_on_best_device(create)
    assert device_module.get_whisper_device().device == "cuda"


def test_transcription_failure_on_gpu_retries_on_cpu(config, gpus, monkeypatch):
    set_count, _ = gpus
    set_count(1)

    def fake_get(force_provider=None):
        return _FakeTranscriber(device_module.get_whisper_device().device, fail_on="cuda")
    monkeypatch.setattr(factory, "get_audio_transcriber", fake_get)

    result, transcriber = factory.transcribe_with_gpu_fallback(Path("talk.mp4"))
    assert result["device"] == "cpu"
    assert transcriber.device == "cpu"
    assert device_module.get_whisper_device().device == "cpu"


def test_non_gpu_errors_are_not_retried(config, gpus, monkeypatch):
    class Broken(_FakeTranscriber):
        def transcribe(self, path, options=None):
            raise ValueError("Unsupported audio format: txt")

    monkeypatch.setattr(factory, "get_audio_transcriber", lambda force_provider=None: Broken("cuda"))
    with pytest.raises(ValueError):
        factory.transcribe_with_gpu_fallback(Path("notes.txt"))
