"""
Docling's half of the GPU feature: `DoclingConverter._apply_accelerator_options`.

`shared/device.py` is well covered on its own, but nothing checked that the
*Docling* path actually asks it. Replacing the `resolve_docling_device()` call
with a hardcoded `"cpu"` used to fail no test at all - which means the DEVICE
setting could silently stop reaching Docling and the suite would say the GPU
feature was fine.

Three properties are pinned here, and they pull in opposite directions, which
is why all three are needed:

  1. The resolved device is what Docling is configured with. Docling's own
     default is `device="auto"`, which grabs `cuda:0` in every worker process
     at once, each with its own CUDA context and its own copy of the
     layout/table weights, and logs nothing. Passing the value explicitly is
     the whole point.
  2. A *docling* problem is swallowed. An older docling with no
     `AcceleratorOptions` still converts documents; it just keeps its own
     device default.
  3. A *DEVICE* problem is NOT swallowed. `DEVICE=cuda` on a box with no CUDA
     is a misconfiguration, and a silent downgrade to CPU turns a 20x slowdown
     into something nobody notices for a month.

No docling and no torch are installed here. Docling is stood in for by a module
that reproduces the one call this code makes - `AcceleratorOptions(device=...,
num_threads=...)` with both keywords required - rather than a mock that would
accept any signature at all.
"""

import sys
import types

import pytest

from shared.config import get_settings
from shared.device import DeviceUnavailableError, reset_device_cache
from workers.converter import DoclingConverter


@pytest.fixture(autouse=True)
def _clean_device_cache():
    """The torch/CUDA probe cache is a module global; no test may leak it."""
    reset_device_cache()
    yield
    reset_device_cache()


@pytest.fixture
def settings_override(monkeypatch):
    """Rebuild Settings from env, dropping the lru_cache on the way in and out."""

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


class _PipelineOptions:
    """The one attribute the code under test writes. Docling's real object has
    dozens more; none of them are touched here."""

    def __init__(self):
        self.accelerator_options = None


@pytest.fixture
def fake_docling(monkeypatch):
    """Stand in for `docling.datamodel.accelerator_options`.

    `AcceleratorOptions` here takes exactly what the real one takes, keyword
    only, and rejects anything else. A MagicMock would accept `AcceleratorOptions()`
    with no arguments at all and happily hide a broken call - this suite already
    has a precedent of a MagicMock swallowing a bad argument and masking a real
    crash.
    """

    class AcceleratorOptions:
        def __init__(self, *, device, num_threads):
            if not isinstance(device, str):
                raise TypeError(f"device must be a str, got {type(device).__name__}")
            if not isinstance(num_threads, int):
                raise TypeError(
                    f"num_threads must be an int, got {type(num_threads).__name__}"
                )
            self.device = device
            self.num_threads = num_threads

    root = types.ModuleType("docling")
    datamodel = types.ModuleType("docling.datamodel")
    accelerator = types.ModuleType("docling.datamodel.accelerator_options")
    accelerator.AcceleratorOptions = AcceleratorOptions
    datamodel.accelerator_options = accelerator
    root.datamodel = datamodel

    monkeypatch.setitem(sys.modules, "docling", root)
    monkeypatch.setitem(sys.modules, "docling.datamodel", datamodel)
    monkeypatch.setitem(sys.modules, "docling.datamodel.accelerator_options", accelerator)
    return AcceleratorOptions


class TestDoclingGetsTheResolvedDevice:
    def test_a_visible_gpu_reaches_docling(self, settings_override, with_cuda, fake_docling):
        """DEVICE=auto with a GPU present: docling must be told `cuda`, by us."""
        settings_override(DEVICE="auto")
        options = _PipelineOptions()

        DoclingConverter._apply_accelerator_options(options)

        assert options.accelerator_options.device == "cuda"

    def test_no_gpu_resolves_to_cpu(self, settings_override, no_cuda, fake_docling):
        settings_override(DEVICE="auto")
        options = _PipelineOptions()

        DoclingConverter._apply_accelerator_options(options)

        assert options.accelerator_options.device == "cpu"

    def test_an_explicit_index_is_passed_through_verbatim(
        self, settings_override, with_cuda, fake_docling
    ):
        """Pinning worker processes to a specific GPU has to survive the trip."""
        settings_override(DEVICE="cuda:1")
        options = _PipelineOptions()

        DoclingConverter._apply_accelerator_options(options)

        assert options.accelerator_options.device == "cuda:1"

    def test_docling_num_threads_comes_from_settings(
        self, settings_override, no_cuda, fake_docling
    ):
        settings = settings_override(DEVICE="cpu", DOCLING_NUM_THREADS="3")
        options = _PipelineOptions()

        DoclingConverter._apply_accelerator_options(options)

        assert options.accelerator_options.num_threads == 3
        assert settings.docling_num_threads == 3

    def test_the_decision_is_logged_with_the_device_it_picked(
        self, settings_override, with_cuda, fake_docling, caplog
    ):
        """The resolved device is the one thing missing from every conversion
        failure report today; it has to be in the log, not only in the object."""
        settings_override(DEVICE="auto")

        with caplog.at_level("INFO", logger="workers.converter"):
            DoclingConverter._apply_accelerator_options(_PipelineOptions())

        assert "device=cuda" in caplog.text


class TestFailureModesAreNotSymmetric:
    def test_an_older_docling_without_accelerator_options_still_converts(
        self, settings_override, no_cuda, monkeypatch
    ):
        """
        Both import sites raise ImportError - the modern one and the legacy
        `pipeline_options` re-export. Docling then keeps its own device
        default, and the conversion goes ahead.
        """
        settings_override(DEVICE="cpu")
        # A None entry makes `import` raise ImportError even where the real
        # docling is installed (the api/worker images); deleting the entry
        # would just let it be imported again from disk.
        for name in (
            "docling.datamodel.accelerator_options",
            "docling.datamodel.pipeline_options",
        ):
            monkeypatch.setitem(sys.modules, name, None)
        options = _PipelineOptions()

        # No exception: a docling shortcoming must never stop a conversion.
        DoclingConverter._apply_accelerator_options(options)

        assert options.accelerator_options is None

    def test_an_unsatisfiable_explicit_device_is_a_hard_error(
        self, settings_override, no_cuda, fake_docling
    ):
        """
        DEVICE=cuda with no CUDA is a misconfiguration, not a preference. It is
        resolved OUTSIDE the try/except for exactly this reason: a silent
        downgrade to CPU is a 20x slowdown nobody notices.
        """
        settings_override(DEVICE="cuda")

        with pytest.raises(DeviceUnavailableError) as exc_info:
            DoclingConverter._apply_accelerator_options(_PipelineOptions())

        assert "DEVICE=cuda" in str(exc_info.value)
