"""
`workers/vision/factory.py` - the process-wide describer and its cache.

Nothing called `get_image_describer()` before this file existed, so every rule
the module's docstring claims to enforce was unverified: the per-provider cache
key, the promise that `force_provider` never repoints the worker, the reset
hook, and the boundary that turns a device problem into a *vision* error.

Two of those are explicitly written up as fixes for defects in
`workers/audio/factory.py`. A documented bug fix with no test is a bug fix that
comes back, and both of them come back silently - a forced provider that writes
the global does not fail anything until the *next, unrelated* request on the
same worker process gets the wrong model.

No torch here, and none needed: building a describer stores strings. The
Florence-2 branch is constructed but never loaded.
"""

import pytest

from shared.config import get_settings
from shared.device import reset_device_cache
from workers.vision import factory
from workers.vision.errors import VisionDeviceUnavailableError
from workers.vision.factory import (
    MIN_TRANSFORMERS_VERSION,
    PROVIDERS,
    get_available_providers,
    get_image_describer,
    reset_image_describer,
)
from workers.vision.florence2_describer import Florence2Describer
from workers.vision.stub_describer import StubDescriber


@pytest.fixture(autouse=True)
def _clean_factory():
    """The describer is a module global. No test may inherit or leak one."""
    reset_image_describer()
    reset_device_cache()
    yield
    reset_image_describer()
    reset_device_cache()


@pytest.fixture
def settings(monkeypatch):
    """The live Settings object, with attributes safe to override per test."""
    return get_settings()


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


class TestTheConfiguredProvider:
    def test_the_configured_provider_is_what_you_get(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "vision_provider", "stub")

        assert isinstance(get_image_describer(), StubDescriber)

    def test_the_instance_is_held_across_calls(self, settings, monkeypatch):
        """
        Rebuilding per call would reload ~0.5GB of weights, and on a GPU that
        is VRAM churn on every request. Identity, not equality.
        """
        monkeypatch.setattr(settings, "vision_provider", "stub")

        assert get_image_describer() is get_image_describer()

    def test_the_provider_name_is_normalised(self, settings, monkeypatch):
        """`VISION_PROVIDER=" Stub "` in a .env is a typo, not a 500."""
        monkeypatch.setattr(settings, "vision_provider", "  Stub  ")

        assert isinstance(get_image_describer(), StubDescriber)

    def test_an_unknown_provider_names_the_ones_that_exist(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "vision_provider", "llava")

        with pytest.raises(ValueError) as exc_info:
            get_image_describer()

        message = str(exc_info.value)
        assert "llava" in message
        assert "VISION_PROVIDER" in message
        for provider in PROVIDERS:
            assert provider in message

    def test_construction_loads_no_weights(self, settings, monkeypatch, no_cuda):
        """`load()` is the only thing that costs anything; the factory is free."""
        monkeypatch.setattr(settings, "vision_provider", "florence2")

        assert get_image_describer().is_loaded is False


class TestForceProviderNeverRepointsTheWorker:
    """
    Defect #1 of the audio factory, fixed here and asserted here.

    In the audio factory `force_provider` writes the global, so one request
    forcing a provider silently repoints that worker process for every
    subsequent request - and nothing fails until much later, somewhere else.
    """

    def test_a_forced_provider_is_a_throwaway(self, settings, monkeypatch, no_cuda):
        monkeypatch.setattr(settings, "vision_provider", "stub")
        cached = get_image_describer()

        forced = get_image_describer(force_provider="florence2")

        assert isinstance(forced, Florence2Describer)
        assert forced is not cached

    def test_the_cached_instance_survives_a_forced_call(
        self, settings, monkeypatch, no_cuda
    ):
        monkeypatch.setattr(settings, "vision_provider", "stub")
        cached = get_image_describer()

        get_image_describer(force_provider="florence2")

        assert get_image_describer() is cached

    def test_forcing_before_anything_is_cached_caches_nothing(
        self, settings, monkeypatch, no_cuda
    ):
        """The order must not matter: forcing first must not seed the cache."""
        monkeypatch.setattr(settings, "vision_provider", "stub")

        get_image_describer(force_provider="florence2")

        assert isinstance(get_image_describer(), StubDescriber)

    def test_forcing_twice_does_not_share_an_instance(self, settings, monkeypatch, no_cuda):
        monkeypatch.setattr(settings, "vision_provider", "stub")

        first = get_image_describer(force_provider="florence2")
        second = get_image_describer(force_provider="florence2")

        assert first is not second


class TestTheCacheIsKeyedOnTheProvider:
    """
    Defect #2 of the audio factory: a cache that ignores which provider it is
    holding hands back the stale instance after the configuration changes.
    """

    def test_changing_the_provider_after_a_reset_gets_the_other_one(
        self, settings, monkeypatch, no_cuda
    ):
        monkeypatch.setattr(settings, "vision_provider", "stub")
        assert isinstance(get_image_describer(), StubDescriber)

        monkeypatch.setattr(settings, "vision_provider", "florence2")
        reset_image_describer()

        assert isinstance(get_image_describer(), Florence2Describer)

    def test_changing_the_provider_without_a_reset_still_gets_the_other_one(
        self, settings, monkeypatch, no_cuda
    ):
        """The key is the provider, so a stale instance cannot be returned even
        when nobody remembered to reset."""
        monkeypatch.setattr(settings, "vision_provider", "stub")
        get_image_describer()

        monkeypatch.setattr(settings, "vision_provider", "florence2")

        assert isinstance(get_image_describer(), Florence2Describer)


class TestReset:
    def test_reset_drops_the_cached_instance(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "vision_provider", "stub")
        first = get_image_describer()

        reset_image_describer()

        assert get_image_describer() is not first

    def test_reset_releases_the_model_reference(self, settings, monkeypatch, no_cuda):
        """
        `torch.cuda.empty_cache()` frees nothing while a live reference to the
        weights exists, so dropping the references is the part that actually
        returns the VRAM - not an optimisation, the whole point.
        """
        monkeypatch.setattr(settings, "vision_provider", "florence2")
        describer = get_image_describer()
        describer._model = object()
        describer._processor = object()

        reset_image_describer()

        assert describer._model is None
        assert describer._processor is None
        assert describer._backend is None

    def test_reset_on_an_empty_cache_is_a_no_op(self):
        reset_image_describer()
        reset_image_describer()


class TestDeviceIsResolvedAtThisBoundary:
    """
    Device policy lives in `shared/device.py`; this is where a device the stack
    cannot satisfy becomes a vision error code the API can turn into a 503.
    """

    def test_an_unsatisfiable_device_becomes_a_vision_error(
        self, settings, monkeypatch, no_cuda
    ):
        monkeypatch.setattr(settings, "vision_provider", "florence2")
        monkeypatch.setattr(settings, "device", "cuda")

        with pytest.raises(VisionDeviceUnavailableError) as exc_info:
            get_image_describer()

        assert exc_info.value.error_code == "VISION_DEVICE_UNAVAILABLE"
        assert exc_info.value.http_status == 503
        # The actionable text shared/device.py wrote has to reach the caller.
        assert "DEVICE=cuda" in str(exc_info.value)

    def test_the_stub_does_not_care_about_the_device(self, settings, monkeypatch, no_cuda):
        """A box with a broken DEVICE must still be able to run the endpoints."""
        monkeypatch.setattr(settings, "vision_provider", "stub")
        monkeypatch.setattr(settings, "device", "cuda")

        assert isinstance(get_image_describer(), StubDescriber)

    def test_cpu_gets_float32(self, settings, monkeypatch, no_cuda):
        """float16 on CPU is slow and numerically unstable for Florence-2."""
        monkeypatch.setattr(settings, "vision_provider", "florence2")
        monkeypatch.setattr(settings, "device", "auto")
        monkeypatch.setattr(settings, "vision_torch_dtype", "auto")

        describer = get_image_describer()

        assert describer.device == "cpu"
        assert describer.dtype == "float32"

    def test_cuda_gets_float16(self, settings, monkeypatch, with_cuda):
        monkeypatch.setattr(settings, "vision_provider", "florence2")
        monkeypatch.setattr(settings, "device", "auto")
        monkeypatch.setattr(settings, "vision_torch_dtype", "auto")

        describer = get_image_describer()

        assert describer.device == "cuda"
        assert describer.dtype == "float16"


class TestTheDescriberIsBuiltFromConfiguration:
    # Every value here is deliberately NOT the shipped default. Asserting
    # against the defaults would pass just as happily if the factory ignored
    # the setting and hardcoded the constant - which is precisely the bug this
    # test has to catch.
    NON_DEFAULT = {
        "vision_model_cache_dir": "/somewhere/else",
        "vision_trust_remote_code": True,
        "vision_allow_model_download": False,
        "vision_max_new_tokens": 77,
        "vision_num_beams": 5,
        "vision_max_image_pixels": 1_234_567,
    }

    def test_florence2_gets_every_setting_it_needs(self, settings, monkeypatch, no_cuda):
        """
        The limits are config, not constants. `max_image_pixels` especially:
        the decompression-bomb guard is only as good as the number it is armed
        with, and the factory is the only thing that arms it.
        """
        monkeypatch.setattr(settings, "vision_provider", "florence2")
        for name, value in self.NON_DEFAULT.items():
            monkeypatch.setattr(settings, name, value)

        describer = get_image_describer()

        assert describer.model_id == settings.vision_model_id
        assert describer.revision == settings.vision_model_revision
        assert describer.cache_dir == "/somewhere/else"
        assert describer.trust_remote_code is True
        assert describer.allow_download is False
        assert describer.max_new_tokens == 77
        assert describer.num_beams == 5
        assert describer.max_image_pixels == 1_234_567

    def test_the_stub_gets_the_configured_caption_task(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "vision_provider", "stub")
        monkeypatch.setattr(settings, "vision_caption_task", "<CAPTION>")

        assert get_image_describer()._task == "<CAPTION>"


class TestAvailabilityProbe:
    """
    Backs `GET /images/capabilities`. It must answer on a machine that cannot
    run the model at all, so it probes module availability and never imports
    torch or loads weights.
    """

    def test_both_providers_are_reported(self):
        report = get_available_providers()

        assert set(report) == set(PROVIDERS)

    def test_the_stub_is_always_available(self):
        assert get_available_providers()["stub"] == {"available": True, "reason": None}

    def test_missing_dependencies_are_named_with_the_fix(self):
        """This suite runs with no torch, which is exactly the operator's case."""
        probe = get_available_providers()["florence2"]

        assert probe["available"] is False
        assert "torch" in probe["reason"]
        assert "requirements-vision.txt" in probe["reason"]

    def test_the_probe_imports_nothing_heavy(self, monkeypatch):
        import sys

        get_available_providers()

        assert "torch" not in sys.modules
        assert "transformers" not in sys.modules

    def test_a_transformers_too_old_for_native_florence2_is_unavailable(self, monkeypatch):
        """
        Below 4.56 there is no `Florence2ForConditionalGeneration`, so the
        default weights-only repo cannot load at all - and the operator needs
        to be told to upgrade, not handed a `trust_remote_code` workaround.
        """
        monkeypatch.setattr(factory.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(factory, "_transformers_version", lambda: (4, 55))

        probe = get_available_providers()["florence2"]

        assert probe["available"] is False
        assert "4.55" in probe["reason"]
        assert "4.56" in probe["reason"]

    def test_the_minimum_version_is_met_at_the_boundary(self, monkeypatch):
        monkeypatch.setattr(factory.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(factory, "_transformers_version", lambda: MIN_TRANSFORMERS_VERSION)

        assert get_available_providers()["florence2"] == {"available": True, "reason": None}

    def test_an_unreadable_version_does_not_block_the_provider(self, monkeypatch):
        """A version string we cannot parse is not evidence of a bad version."""
        monkeypatch.setattr(factory.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(factory, "_transformers_version", lambda: None)

        assert get_available_providers()["florence2"]["available"] is True

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("4.56.1", (4, 56)),
            ("4.57", (4, 57)),
            ("5.0.0.dev0", (5, 0)),
            ("4.56.0rc1", (4, 56)),
            ("weird", None),
        ],
    )
    def test_version_parsing(self, monkeypatch, raw, expected):
        """Read from metadata, not by importing transformers - this runs behind
        a capabilities probe and has to stay cheap."""
        import importlib.metadata

        monkeypatch.setattr(importlib.metadata, "version", lambda name: raw)

        assert factory._transformers_version() == expected
