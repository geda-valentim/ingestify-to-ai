"""
The CTranslate2 capability guard in shared/device.py — spec 0002.

The guard this replaces used ``ctranslate2.get_cuda_device_count() > 0``, which
binds to ``cudaGetDeviceCount()``: it counts VISIBLE GPUs and says nothing about
cuDNN. Its central failure was the case exercised by
``test_cuda_visible_but_no_compute_type_falls_back``: a host where the GPU is
perfectly visible and ``faster-whisper`` still dies on
``Unable to load libcudnn_ops.so.9``.

``ctranslate2`` is a fake ``types.ModuleType`` injected into ``sys.modules`` and
``ctypes.CDLL`` is monkeypatched, so nothing here needs a GPU, a real
ctranslate2, or torch.
"""

import logging
import sys
import types

import pytest

from shared.config import get_settings
from shared.device import (
    _ctranslate2_cuda_blocker,
    _cudnn9_load_error,
    reset_device_cache,
    resolve_whisper_device,
)


@pytest.fixture(autouse=True)
def _clean_device_cache():
    reset_device_cache()
    yield
    reset_device_cache()


@pytest.fixture
def settings_override(monkeypatch):
    def _apply(**env):
        get_settings.cache_clear()
        for key, value in env.items():
            monkeypatch.setenv(key.upper(), value)
        return get_settings()

    yield _apply
    get_settings.cache_clear()


@pytest.fixture
def with_cuda(monkeypatch):
    monkeypatch.setattr("shared.device.cuda_available", lambda: True)
    monkeypatch.setattr("shared.device.torch_available", lambda: True)
    monkeypatch.setattr("shared.device._cuda_device_name", lambda: "NVIDIA Test GPU")
    monkeypatch.setattr("shared.device._cuda_device_count", lambda: 2)


@pytest.fixture
def cudnn_ok(monkeypatch):
    """cuDNN 9 loads. Isolates the ctranslate2 half of the guard."""
    monkeypatch.setattr("shared.device._cudnn9_load_error", lambda: None)


@pytest.fixture
def fake_ct2(monkeypatch):
    """Install a fake ``ctranslate2`` module and hand it to the test."""

    def _install(**attrs):
        module = types.ModuleType("ctranslate2")
        for name, value in attrs.items():
            setattr(module, name, value)
        monkeypatch.setitem(sys.modules, "ctranslate2", module)
        return module

    return _install


def _raiser(exc):
    def _fn(*args, **kwargs):
        raise exc

    return _fn


# --- _ctranslate2_cuda_blocker ---------------------------------------------


class TestBlocker:
    def test_missing_ctranslate2_is_a_blocker(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "ctranslate2", None)
        blocker = _ctranslate2_cuda_blocker()
        assert blocker is not None
        assert "ctranslate2" in blocker

    def test_the_device_count_is_no_longer_consulted(self, fake_ct2, cudnn_ok):
        """The old guard's only input must not be able to decide anything.

        A module whose device count is 0 but whose CUDA compute types are real
        passes; a module whose device count is 99 but which cannot offer a CUDA
        compute type does not. Both are the inverse of the old behaviour.
        """
        fake_ct2(
            get_cuda_device_count=lambda: 0,
            get_supported_compute_types=lambda device: {"float16", "int8_float16"},
        )
        assert _ctranslate2_cuda_blocker() is None

        fake_ct2(
            get_cuda_device_count=lambda: 99,
            get_supported_compute_types=lambda device: set(),
        )
        assert _ctranslate2_cuda_blocker() is not None

    def test_compute_types_raising_is_a_blocker(self, fake_ct2, cudnn_ok):
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=_raiser(RuntimeError("no CUDA runtime")),
        )
        blocker = _ctranslate2_cuda_blocker()
        assert blocker is not None
        assert "no CUDA runtime" in blocker

    def test_empty_compute_types_is_a_blocker(self, fake_ct2, cudnn_ok):
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: [],
        )
        assert _ctranslate2_cuda_blocker() == "ctranslate2 offers no CUDA compute type"

    def test_unloadable_cudnn_is_a_blocker(self, fake_ct2, monkeypatch):
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16"},
        )
        monkeypatch.setattr(
            "shared.device._cudnn9_load_error",
            lambda: "libcudnn_ops.so.9: cannot open shared object file",
        )
        blocker = _ctranslate2_cuda_blocker()
        assert blocker is not None
        assert "libcudnn_ops.so.9" in blocker

    def test_a_healthy_stack_has_no_blocker(self, fake_ct2, cudnn_ok):
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16", "float32"},
        )
        assert _ctranslate2_cuda_blocker() is None

    def test_it_asks_ctranslate2_about_cuda_specifically(self, fake_ct2, cudnn_ok):
        seen = []
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: seen.append(device)
            or {"float16"},
        )
        _ctranslate2_cuda_blocker()
        assert seen == ["cuda"]


# --- _cudnn9_load_error ----------------------------------------------------


class TestCudnnProbe:
    def test_it_prefers_the_wheel_path_over_the_bare_soname(self, monkeypatch):
        """The nvidia-cudnn-cu12 wheel's copy is normally NOT on the system
        loader path, so a bare-soname-only probe would report a false failure on
        a healthy GPU install."""
        nvidia = types.ModuleType("nvidia")
        nvidia.__path__ = []  # make it a package so `nvidia.cudnn` can be set
        cudnn = types.ModuleType("nvidia.cudnn")
        cudnn.__file__ = "/fake/site-packages/nvidia/cudnn/__init__.py"
        nvidia.cudnn = cudnn
        monkeypatch.setitem(sys.modules, "nvidia", nvidia)
        monkeypatch.setitem(sys.modules, "nvidia.cudnn", cudnn)

        tried = []

        def _cdll(name, *args, **kwargs):
            tried.append(name)
            return object()

        monkeypatch.setattr("ctypes.CDLL", _cdll)

        assert _cudnn9_load_error() is None
        assert tried == ["/fake/site-packages/nvidia/cudnn/lib/libcudnn_ops.so.9"]

    def test_it_falls_back_to_the_soname_when_nvidia_cudnn_is_absent(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "nvidia.cudnn", None)
        tried = []

        def _cdll(name, *args, **kwargs):
            tried.append(name)
            return object()

        monkeypatch.setattr("ctypes.CDLL", _cdll)

        assert _cudnn9_load_error() is None
        assert tried == ["libcudnn_ops.so.9"]

    def test_it_reports_the_loader_error_instead_of_raising(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "nvidia.cudnn", None)
        monkeypatch.setattr(
            "ctypes.CDLL",
            _raiser(OSError("libcudnn_ops.so.9: cannot open shared object file")),
        )
        error = _cudnn9_load_error()
        assert error is not None
        assert "cannot open shared object file" in error


# --- resolve_whisper_device end to end -------------------------------------


class TestWhisperFallback:
    def test_cuda_visible_but_no_compute_type_falls_back(
        self, settings_override, with_cuda, fake_ct2, cudnn_ok, caplog
    ):
        """THE case the old guard missed: `get_cuda_device_count()` would have
        returned 4 here and the fallback would never have fired."""
        settings_override(DEVICE="cuda", WHISPER_DEVICE="")
        fake_ct2(
            get_cuda_device_count=lambda: 4,
            get_supported_compute_types=lambda device: set(),
        )

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            assert resolve_whisper_device() == "cpu"

        assert "falling back to cpu" in caplog.text
        assert "no CUDA compute type" in caplog.text
        assert "requirements-cuda.txt" in caplog.text

    def test_cuda_visible_but_cudnn_unloadable_falls_back(
        self, settings_override, with_cuda, fake_ct2, monkeypatch, caplog
    ):
        settings_override(DEVICE="cuda", WHISPER_DEVICE="")
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16"},
        )
        monkeypatch.setattr(
            "shared.device._cudnn9_load_error", lambda: "wrong cuDNN tree"
        )

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            assert resolve_whisper_device() == "cpu"

        assert "libcudnn_ops.so.9" in caplog.text

    def test_an_explicit_cuda_request_also_falls_back_rather_than_500ing(
        self, settings_override, with_cuda, fake_ct2, cudnn_ok, caplog
    ):
        """WHISPER_DEVICE=cuda cannot conjure a working cuDNN. Failing every
        transcription instead of degrading is not a better answer."""
        settings_override(DEVICE="cpu", WHISPER_DEVICE="cuda")
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=_raiser(RuntimeError("CUDA driver error")),
        )

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            assert resolve_whisper_device() == "cpu"

        assert "falling back to cpu" in caplog.text

    def test_a_healthy_stack_keeps_cuda(
        self, settings_override, with_cuda, fake_ct2, cudnn_ok
    ):
        settings_override(DEVICE="cuda", WHISPER_DEVICE="")
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16"},
        )
        assert resolve_whisper_device() == "cuda"

    def test_the_guard_is_not_reached_on_cpu(self, settings_override, monkeypatch):
        """No CUDA, no probing: the blocker must not run on the common path."""
        monkeypatch.setattr("shared.device.cuda_available", lambda: False)
        monkeypatch.setattr("shared.device.torch_available", lambda: False)
        monkeypatch.setattr(
            "shared.device._ctranslate2_cuda_blocker",
            _raiser(AssertionError("the blocker must not run for a cpu device")),
        )
        settings_override(DEVICE="auto", WHISPER_DEVICE="")
        assert resolve_whisper_device() == "cpu"


# --- the migration signal --------------------------------------------------


class TestMigrationWarning:
    def test_inheriting_cuda_warns_that_the_behaviour_changed(
        self, settings_override, with_cuda, fake_ct2, cudnn_ok, caplog
    ):
        """WHISPER_DEVICE did not exist before spec 0002, so NOBODY has it set:
        this is the whole upgrading population, and config.py's boot WARNING
        cannot reach it because that only fires for a non-empty value."""
        settings_override(DEVICE="cuda", WHISPER_DEVICE="")
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16"},
        )

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            assert resolve_whisper_device() == "cuda"

        assert "transcription now runs on cuda" in caplog.text
        assert "hardcoded to cpu" in caplog.text
        # It must say how to opt out, not merely that something changed.
        assert "WHISPER_DEVICE=cpu" in caplog.text

    def test_the_migration_warning_is_emitted_once(
        self, settings_override, with_cuda, fake_ct2, cudnn_ok, caplog
    ):
        settings_override(DEVICE="cuda", WHISPER_DEVICE="")
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16"},
        )

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            for _ in range(5):
                resolve_whisper_device()

        assert caplog.text.count("transcription now runs on") == 1

    def test_no_migration_warning_when_the_user_pinned_cuda(
        self, settings_override, with_cuda, fake_ct2, cudnn_ok, caplog
    ):
        """They asked for it explicitly; nothing changed under them."""
        settings_override(DEVICE="cpu", WHISPER_DEVICE="cuda")
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16"},
        )

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            assert resolve_whisper_device() == "cuda"

        assert "transcription now runs on" not in caplog.text

    def test_no_migration_warning_when_audio_stays_on_cpu(
        self, settings_override, monkeypatch, caplog
    ):
        monkeypatch.setattr("shared.device.cuda_available", lambda: False)
        monkeypatch.setattr("shared.device.torch_available", lambda: False)
        settings_override(DEVICE="auto", WHISPER_DEVICE="")

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            assert resolve_whisper_device() == "cpu"

        assert "transcription now runs on" not in caplog.text

    def test_no_migration_warning_when_the_guard_fell_back(
        self, settings_override, with_cuda, fake_ct2, cudnn_ok, caplog
    ):
        """Falling back to CPU restores the pre-0002 behaviour, so there is
        nothing to migrate — only the blocker WARNING should appear."""
        settings_override(DEVICE="cuda", WHISPER_DEVICE="")
        fake_ct2(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: set(),
        )

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            assert resolve_whisper_device() == "cpu"

        assert "transcription now runs on" not in caplog.text
