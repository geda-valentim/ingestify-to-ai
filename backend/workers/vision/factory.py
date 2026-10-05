"""
Factory for image describer instances.

Follows the shape of ``workers/audio/factory.py`` - a configured provider, a
process-wide singleton, a reset hook for tests - with its two defects fixed:

1. ``force_provider`` NEVER writes the global. In the audio factory it does,
   so a single request forcing a provider silently repoints that worker process
   for every subsequent request. Here a forced provider yields a throwaway
   instance and the cached one is left alone.
2. The cache is keyed on the resolved provider name, so changing
   ``VISION_PROVIDER`` and resetting actually gets you the other provider
   instead of the stale instance.

Holding the instance matters more here than it does for audio: rebuilding a
describer per call would reload ~0.5GB of weights, and on a GPU that is VRAM
churn on every request.
"""

import importlib.util
import logging
from typing import Any, Dict, Optional

from workers.vision.base_describer import ImageDescriber
from workers.vision.errors import VisionDeviceUnavailableError

logger = logging.getLogger(__name__)

# transformers gained a native Florence2ForConditionalGeneration in 4.56; below
# that, loading the default (weights-only, no custom code) repo cannot work.
MIN_TRANSFORMERS_VERSION = (4, 56)

PROVIDERS = ("florence2", "stub")

_describer_instance: Optional[ImageDescriber] = None
_describer_provider: Optional[str] = None


def get_image_describer(force_provider: Optional[str] = None) -> ImageDescriber:
    """Get the process-wide describer, building it on first use.

    Args:
        force_provider: Build and return a throwaway instance of this provider
            instead of the configured one. Does not disturb the cached
            instance - a caller forcing a provider must not repoint the worker.

    Returns:
        An ImageDescriber. Weights are NOT loaded here; call ``load()`` (or let
        ``describe()``/``ocr()`` do it) so construction stays free.

    Raises:
        ValueError: The provider name is unknown.
        VisionDeviceUnavailableError: DEVICE names a GPU that torch cannot use.
    """
    global _describer_instance, _describer_provider

    from shared.config import get_settings

    settings = get_settings()
    provider = (force_provider or settings.vision_provider).strip().lower()

    if force_provider:
        return _build_describer(provider, settings)

    if _describer_instance is not None and _describer_provider == provider:
        return _describer_instance

    instance = _build_describer(provider, settings)
    _describer_instance = instance
    _describer_provider = provider
    return instance


def peek_image_describer() -> Optional[ImageDescriber]:
    """The cached instance, or None. Never builds one, never writes the global.

    For observers - the capabilities heartbeat asks this from a background
    thread, and a probe must not be able to construct (or race the construction
    of) the instance that holds the loaded weights.
    """
    return _describer_instance


def _build_describer(provider: str, settings) -> ImageDescriber:
    """Construct a describer. Cheap: no weights, no torch import."""
    if provider == "stub":
        from workers.vision.stub_describer import StubDescriber

        logger.info("vision: using the stub describer (VISION_PROVIDER=stub)")
        return StubDescriber(task=settings.vision_caption_task)

    if provider == "florence2":
        from workers.vision.florence2_describer import Florence2Describer

        device, dtype = _resolve_device_and_dtype()
        logger.info(
            "vision: provider=florence2 model=%s@%s device=%s dtype=%s",
            settings.vision_model_id,
            settings.vision_model_revision[:8],
            device,
            dtype,
        )
        return Florence2Describer(
            model_id=settings.vision_model_id,
            revision=settings.vision_model_revision,
            device=device,
            dtype=dtype,
            cache_dir=settings.vision_model_cache_dir,
            trust_remote_code=settings.vision_trust_remote_code,
            allow_download=settings.vision_allow_model_download,
            max_new_tokens=settings.vision_max_new_tokens,
            num_beams=settings.vision_num_beams,
            max_image_pixels=settings.vision_max_image_pixels,
        )

    raise ValueError(
        f"Unknown vision provider: {provider}. "
        f"Supported providers: {', '.join(PROVIDERS)} (set VISION_PROVIDER)."
    )


def _resolve_device_and_dtype() -> tuple:
    """Ask shared.device, and translate its failure into a vision error.

    Device policy lives in exactly one module. This is the boundary where a
    DEVICE the stack cannot satisfy becomes a 503 with a vision error code.
    """
    from shared.device import DeviceUnavailableError, resolve_device, resolve_dtype_name

    try:
        device = resolve_device()
    except DeviceUnavailableError as exc:
        raise VisionDeviceUnavailableError(str(exc)) from exc

    return device, resolve_dtype_name(device)


def reset_image_describer() -> None:
    """Drop the cached describer and free any GPU memory it held.

    Tests use this; so does anything that changes provider configuration at
    runtime. Releasing the model reference before emptying the CUDA cache is
    what actually returns the VRAM - empty_cache() alone frees nothing while a
    live reference exists.
    """
    global _describer_instance, _describer_provider

    instance = _describer_instance
    _describer_instance = None
    _describer_provider = None

    if instance is None:
        return

    device = ""
    try:
        device = str(instance.info().get("device", ""))
    except Exception:  # pragma: no cover - info() is trivial for both providers
        pass

    # Drop the heavy references before asking the allocator for anything back.
    for attribute in ("_model", "_processor", "_torch_dtype", "_backend"):
        if hasattr(instance, attribute):
            setattr(instance, attribute, None)

    if device.startswith("cuda"):
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception as exc:  # pragma: no cover - depends on live CUDA
            logger.debug("vision: could not empty the CUDA cache: %s", exc)

    logger.info("vision: describer instance reset")


def get_available_providers() -> Dict[str, Dict[str, Any]]:
    """Report which providers this process could actually build.

    Probes module availability only - never imports torch and never loads
    weights, so it is safe to call from a capabilities endpoint.
    """
    return {
        "florence2": _probe_florence2(),
        "stub": {"available": True, "reason": None},
    }


def _probe_florence2() -> Dict[str, Any]:
    missing = [
        name
        for name, module in (("torch", "torch"), ("transformers", "transformers"), ("Pillow", "PIL"))
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        return {
            "available": False,
            "reason": (
                f"missing dependencies: {', '.join(missing)}. Install the vision extra: "
                "pip install -r backend/requirements-vision.txt (CPU) or "
                "backend/requirements-vision-cuda.txt (NVIDIA GPU)."
            ),
        }

    version = _transformers_version()
    if version is not None and version < MIN_TRANSFORMERS_VERSION:
        installed = ".".join(str(part) for part in version)
        required = ".".join(str(part) for part in MIN_TRANSFORMERS_VERSION)
        return {
            "available": False,
            "reason": (
                f"transformers {installed} has no native Florence-2 support "
                f"(requires >= {required}). Upgrade with: "
                "pip install -r backend/requirements-vision.txt"
            ),
        }

    return {"available": True, "reason": None}


def _transformers_version():
    """The installed transformers version as (major, minor), or None if unreadable.

    Read from package metadata rather than by importing transformers: this runs
    behind a capabilities probe and must stay cheap.
    """
    try:
        from importlib.metadata import version

        raw = version("transformers")
    except Exception:
        return None

    parts = []
    for piece in raw.split(".")[:2]:
        digits = "".join(char for char in piece if char.isdigit())
        if not digits:
            return None
        parts.append(int(digits))

    return tuple(parts) if len(parts) == 2 else None
