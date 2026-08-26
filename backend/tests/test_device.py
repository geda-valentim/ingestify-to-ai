"""
Tests for shared/device.py - the single device-resolution point.

Rules under test:
  * `auto` never fails: it degrades to CPU when CUDA is not usable.
  * an explicit `cuda` DOES fail rather than silently downgrading.
  * WHISPER_DEVICE keeps overriding DEVICE for anyone who already set it.
  * the module imports cleanly with torch absent.

No test here may require a real GPU, and none may import torch.
"""

import logging
import subprocess
import sys
import types
from pathlib import Path

import pytest

from shared.config import Settings, get_settings
from shared.device import (
    DeviceUnavailableError,
    cuda_available,
    device_report,
    reset_device_cache,
    resolve_device,
    resolve_docling_device,
    resolve_dtype_name,
    resolve_whisper_compute_type,
    resolve_whisper_device,
    torch_available,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_device_cache():
    """The probe cache is a module global; no test may leak it into the next."""
    reset_device_cache()
    yield
    reset_device_cache()


@pytest.fixture
def settings_override(monkeypatch):
    """Rebuild Settings from env, and drop the lru_cache on the way in and out."""

    def _apply(**env):
        get_settings.cache_clear()
        for key, value in env.items():
            monkeypatch.setenv(key.upper(), value)
        return get_settings()

    yield _apply
    get_settings.cache_clear()


@pytest.fixture
def no_cuda(monkeypatch):
    monkeypatch.setattr("shared.device.cuda_available", lambda: False)
    monkeypatch.setattr("shared.device.torch_available", lambda: False)


@pytest.fixture
def with_cuda(monkeypatch):
    monkeypatch.setattr("shared.device.cuda_available", lambda: True)
    monkeypatch.setattr("shared.device.torch_available", lambda: True)
    monkeypatch.setattr("shared.device._cuda_device_name", lambda: "NVIDIA Test GPU")
    monkeypatch.setattr("shared.device._cuda_device_count", lambda: 2)


# --- resolve_device --------------------------------------------------------


class TestResolveDevice:
    def test_auto_with_cuda_available_resolves_to_cuda(self, with_cuda, caplog):
        with caplog.at_level(logging.INFO, logger="shared.device"):
            assert resolve_device("auto") == "cuda"
        assert "device=cuda" in caplog.text
        assert "NVIDIA Test GPU" in caplog.text

    def test_auto_without_cuda_falls_back_to_cpu(self, no_cuda, caplog):
        with caplog.at_level(logging.INFO, logger="shared.device"):
            assert resolve_device("auto") == "cpu"
        # The fallback must be visible: it is the difference between a working
        # box and a mysteriously slow one.
        assert "device=cpu" in caplog.text
        assert "torch.cuda unavailable" in caplog.text

    def test_explicit_cpu_is_honoured_even_with_a_gpu_present(self, with_cuda):
        assert resolve_device("cpu") == "cpu"

    def test_explicit_cuda_without_cuda_is_a_hard_error(self, no_cuda):
        with pytest.raises(DeviceUnavailableError) as exc:
            resolve_device("cuda")
        message = str(exc.value)
        assert "no usable CUDA device" in message
        assert "torch installed: no" in message
        # The message has to say what to do about it.
        assert "requirements-cuda.txt" in message
        assert "DEVICE=auto" in message

    def test_explicit_indexed_cuda_without_cuda_is_a_hard_error(self, no_cuda):
        with pytest.raises(DeviceUnavailableError):
            resolve_device("cuda:1")

    def test_explicit_cuda_with_cuda_is_returned_as_given(self, with_cuda):
        assert resolve_device("cuda") == "cuda"
        assert resolve_device("cuda:1") == "cuda:1"

    def test_out_of_range_cuda_index_is_rejected(self, with_cuda):
        # 2 devices reported, so cuda:5 cannot be satisfied.
        with pytest.raises(DeviceUnavailableError) as exc:
            resolve_device("cuda:5")
        assert "only 2 CUDA device(s)" in str(exc.value)

    def test_unknown_value_raises_value_error_naming_the_accepted_values(self, no_cuda):
        with pytest.raises(ValueError) as exc:
            resolve_device("mps")
        assert "cuda:N" in str(exc.value)

    def test_case_and_whitespace_are_tolerated(self, with_cuda):
        assert resolve_device("  CUDA  ") == "cuda"

    def test_none_reads_the_device_setting(self, settings_override, no_cuda):
        settings_override(DEVICE="cpu")
        assert resolve_device() == "cpu"
        assert resolve_docling_device() == "cpu"

    def test_repeated_resolution_logs_once(self, no_cuda, caplog):
        with caplog.at_level(logging.INFO, logger="shared.device"):
            for _ in range(5):
                resolve_device("auto")
        # Per page job across 10 processes, one line per decision is the budget.
        assert caplog.text.count("device=cpu") == 1


# --- probes ----------------------------------------------------------------


class TestProbes:
    def test_cuda_available_is_false_when_torch_is_missing(self, monkeypatch):
        monkeypatch.setattr("shared.device.torch_available", lambda: False)
        reset_device_cache()
        assert cuda_available() is False

    def test_cuda_available_swallows_a_broken_driver(self, monkeypatch):
        """A mismatched libcuda raises; it does not return False."""
        fake_torch = types.ModuleType("torch")
        fake_torch.cuda = types.SimpleNamespace(
            is_available=lambda: (_ for _ in ()).throw(RuntimeError("libcuda.so.1 missing"))
        )
        monkeypatch.setitem(sys.modules, "torch", fake_torch)
        reset_device_cache()
        assert cuda_available() is False

    def test_probes_are_cached(self, monkeypatch):
        calls = []

        fake_torch = types.ModuleType("torch")
        fake_torch.__version__ = "2.13.0"

        def _is_available():
            calls.append(1)
            return False

        fake_torch.cuda = types.SimpleNamespace(is_available=_is_available)
        monkeypatch.setitem(sys.modules, "torch", fake_torch)
        reset_device_cache()

        for _ in range(4):
            cuda_available()

        assert len(calls) == 1


# --- dtype -----------------------------------------------------------------


class TestResolveDtypeName:
    def test_auto_is_float16_on_cuda(self):
        assert resolve_dtype_name("cuda", "auto") == "float16"
        assert resolve_dtype_name("cuda:1", "auto") == "float16"

    def test_auto_is_float32_on_cpu(self):
        # float16 on CPU is slow and numerically unstable for Florence-2.
        assert resolve_dtype_name("cpu", "auto") == "float32"

    def test_explicit_value_wins(self):
        assert resolve_dtype_name("cpu", "bfloat16") == "bfloat16"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            resolve_dtype_name("cpu", "int8")

    def test_none_reads_the_setting(self, settings_override):
        settings_override(VISION_TORCH_DTYPE="float32")
        assert resolve_dtype_name("cuda") == "float32"

    def test_it_returns_a_string_not_a_torch_object(self):
        assert isinstance(resolve_dtype_name("cpu", "auto"), str)


# --- whisper ---------------------------------------------------------------


class TestWhisperDevice:
    def test_empty_whisper_device_inherits_device(self, settings_override, no_cuda):
        settings_override(DEVICE="cpu", WHISPER_DEVICE="")
        assert resolve_whisper_device() == "cpu"

    def test_non_empty_whisper_device_overrides_device(self, settings_override, with_cuda):
        # An existing .env that pinned WHISPER_DEVICE=cpu keeps its exact
        # current behaviour even on a GPU box.
        settings_override(DEVICE="cuda", WHISPER_DEVICE="cpu")
        assert resolve_whisper_device() == "cpu"

    def test_the_override_is_logged_on_every_boot(self, monkeypatch, caplog):
        monkeypatch.setenv("WHISPER_DEVICE", "cpu")
        monkeypatch.setenv("DEVICE", "cuda")
        with caplog.at_level(logging.WARNING, logger="shared.config"):
            Settings()
        assert "WHISPER_DEVICE=cpu overrides DEVICE=cuda" in caplog.text
        assert "unset it to follow DEVICE" in caplog.text

    def test_no_warning_when_whisper_device_is_unset(self, monkeypatch, caplog):
        monkeypatch.setenv("WHISPER_DEVICE", "")
        with caplog.at_level(logging.WARNING, logger="shared.config"):
            Settings()
        assert "WHISPER_DEVICE" not in caplog.text

    def test_cuda_falls_back_to_cpu_when_ctranslate2_cannot_use_it(
        self, settings_override, with_cuda, monkeypatch, caplog
    ):
        """faster-whisper on CUDA dies with `Unable to load libcudnn_ops.so.9`;
        a logged CPU fallback beats a 500 on every transcription."""
        settings_override(DEVICE="cuda", WHISPER_DEVICE="")
        fake_ct2 = types.ModuleType("ctranslate2")
        fake_ct2.get_cuda_device_count = lambda: 0
        monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)

        with caplog.at_level(logging.WARNING, logger="shared.device"):
            assert resolve_whisper_device() == "cpu"
        assert "ctranslate2 reports no CUDA device" in caplog.text

    def test_cuda_is_kept_when_ctranslate2_can_use_it(
        self, settings_override, with_cuda, monkeypatch
    ):
        settings_override(DEVICE="cuda", WHISPER_DEVICE="")
        fake_ct2 = types.ModuleType("ctranslate2")
        fake_ct2.get_cuda_device_count = lambda: 1
        monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)

        assert resolve_whisper_device() == "cuda"

    def test_explicit_cuda_whisper_device_without_cuda_still_raises(
        self, settings_override, no_cuda
    ):
        settings_override(DEVICE="cpu", WHISPER_DEVICE="cuda")
        with pytest.raises(DeviceUnavailableError):
            resolve_whisper_device()


class TestWhisperComputeType:
    def test_derived_from_the_resolved_device(self, settings_override):
        settings_override(WHISPER_COMPUTE_TYPE="")
        assert resolve_whisper_compute_type("cpu") == "int8"
        assert resolve_whisper_compute_type("cuda") == "float16"
        assert resolve_whisper_compute_type("cuda:1") == "float16"

    def test_explicit_value_wins(self, settings_override):
        settings_override(WHISPER_COMPUTE_TYPE="float32")
        assert resolve_whisper_compute_type("cuda") == "float32"


# --- report ----------------------------------------------------------------


class TestDeviceReport:
    def test_report_shape(self, settings_override, no_cuda):
        settings_override(DEVICE="auto")
        report = device_report()
        assert set(report) == {
            "requested",
            "resolved",
            "torch_available",
            "cuda_available",
            "torch_version",
            "cuda_device_name",
            "reason",
        }
        assert report["requested"] == "auto"
        assert report["resolved"] == "cpu"

    def test_report_never_raises_on_a_bad_device(self, settings_override, no_cuda):
        # An ops probe must not blow up describing a broken configuration.
        settings_override(DEVICE="cuda")
        report = device_report()
        assert report["resolved"] == "cpu"
        assert "no usable CUDA device" in report["reason"]


# --- config validation -----------------------------------------------------


class TestDeviceSetting:
    @pytest.mark.parametrize("value", ["auto", "cpu", "cuda", "cuda:0", "cuda:3"])
    def test_accepted_values(self, monkeypatch, value):
        monkeypatch.setenv("DEVICE", value)
        assert Settings().device == value

    @pytest.mark.parametrize("value", ["gpu", "mps", "cuda:", "cuda:x", "CUDA:1:2", ""])
    def test_rejected_values(self, monkeypatch, value):
        monkeypatch.setenv("DEVICE", value)
        with pytest.raises(Exception) as exc:
            Settings()
        assert "DEVICE" in str(exc.value)

    def test_default_is_auto(self, monkeypatch):
        monkeypatch.delenv("DEVICE", raising=False)
        assert Settings().device == "auto"

    def test_vision_model_id_override_without_a_new_revision_is_rejected(self, monkeypatch):
        """This is what stops a floating-branch pull sneaking in."""
        monkeypatch.setenv("VISION_MODEL_ID", "florence-community/Florence-2-large-ft")
        monkeypatch.delenv("VISION_MODEL_REVISION", raising=False)
        with pytest.raises(Exception) as exc:
            Settings()
        assert "VISION_MODEL_REVISION" in str(exc.value)

    def test_vision_model_id_override_with_a_new_revision_is_accepted(self, monkeypatch):
        monkeypatch.setenv("VISION_MODEL_ID", "florence-community/Florence-2-large-ft")
        monkeypatch.setenv(
            "VISION_MODEL_REVISION", "26b734a54fdfbf9c398351eedfabb7f27fc470b7"
        )
        assert Settings().vision_model_id == "florence-community/Florence-2-large-ft"


# --- the one that matters --------------------------------------------------


def test_module_imports_cleanly_when_torch_cannot_be_imported():
    """
    shared/device.py is copied into both Dockerfiles and must import on a box
    with no torch at all. A module-level `import torch` would break the API
    container, which is deliberately CPU-only and may not have torch installed.

    Run in a subprocess with a meta_path hook that makes `import torch` raise,
    because a torch already imported into this process cannot be un-imported.
    """
    script = """
import sys

class BlockTorch:
    def find_module(self, name, path=None):
        return self.find_spec(name, path)
    def find_spec(self, name, path=None, target=None):
        if name == "torch" or name.startswith("torch."):
            raise ImportError("No module named 'torch' (blocked by test)")
        return None

sys.meta_path.insert(0, BlockTorch())
sys.modules.pop("torch", None)

import shared.device as d

assert d.torch_available() is False, "torch_available must be False"
assert d.cuda_available() is False, "cuda_available must be False"
assert d.resolve_device("auto") == "cpu", "auto must degrade to cpu"
assert d.resolve_device("cpu") == "cpu"
assert d.resolve_dtype_name("cpu", "auto") == "float32"
try:
    d.resolve_device("cuda")
except d.DeviceUnavailableError as e:
    assert "torch installed: no" in str(e), str(e)
else:
    raise AssertionError("explicit cuda must raise without torch")

report = d.device_report()
assert report["resolved"] == "cpu"
assert report["torch_available"] is False
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(BACKEND_ROOT),
            "JWT_SECRET_KEY": "test-only-secret-not-for-any-real-environment-0123456789abcdef",
            "MINIO_ACCESS_KEY": "test-access-key",
            "MINIO_SECRET_KEY": "test-secret-key",
        },
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "OK" in result.stdout
