"""
Single source of truth for "which device does this run on?".

Every component that can use a GPU (Docling, Whisper, Florence-2) asks this
module and nothing else. Before this existed the answer was spread across three
places -- docling resolved ``auto`` internally, ``openai_whisper_transcriber``
probed ``torch.cuda.is_available()`` itself, and ``faster-whisper`` was pinned
to CPU by a config default -- and none of them logged what they picked.

Design rules this module has to keep:

1. It MUST import cleanly with torch absent. ``import torch`` appears only
   inside function bodies, guarded by ``try/except ImportError``. Dtypes cross
   this module's API as strings so no signature ever mentions a torch type.
2. It MUST NOT import ``shared.config`` at module level; ``get_settings()`` is
   called inside functions, exactly as ``workers/audio/factory.py`` does.
3. Probing happens once and is cached. ``torch.cuda.is_available()`` costs a
   driver init, and calling it per page job across 10 worker processes is
   measurable.
4. Every fallback and every override logs, naming both the requested and the
   resolved device.
"""

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CPU = "cpu"
CUDA = "cuda"


class DeviceUnavailableError(RuntimeError):
    """An explicitly requested device cannot be provided. Never raised for 'auto'."""


# --- probe cache -----------------------------------------------------------
# Guarded because Celery prefork workers may resolve concurrently from threads.
_lock = threading.Lock()
_torch_available: Optional[bool] = None
_cuda_available: Optional[bool] = None
# Decisions already logged, so a per-page-job resolve() does not flood the log.
_logged_decisions: set = set()


def reset_device_cache() -> None:
    """Clear the probe cache. Tests only, mirroring reset_audio_transcriber()."""
    global _torch_available, _cuda_available
    with _lock:
        _torch_available = None
        _cuda_available = None
        _logged_decisions.clear()


def torch_available() -> bool:
    """True iff ``import torch`` succeeds. Cached. Never raises."""
    global _torch_available
    if _torch_available is None:
        try:
            import torch  # noqa: F401

            _torch_available = True
        except Exception:  # ImportError, but a broken build can raise anything
            _torch_available = False
    return _torch_available


def cuda_available() -> bool:
    """
    True iff torch reports at least one usable CUDA device. Cached.

    False when torch is missing. ``torch.cuda.is_available()`` is wrapped in a
    broad except because a broken driver or a mismatched libcuda raises rather
    than returning False.
    """
    global _cuda_available
    if _cuda_available is None:
        if not torch_available():
            _cuda_available = False
        else:
            try:
                import torch

                _cuda_available = bool(torch.cuda.is_available())
            except Exception as exc:
                logger.warning("torch.cuda.is_available() raised: %s", exc)
                _cuda_available = False
    return _cuda_available


def _log_once(key: str, level: int, message: str, *args: Any) -> None:
    """Emit a device decision the first time it is reached in this process."""
    with _lock:
        if key in _logged_decisions:
            return
        _logged_decisions.add(key)
    logger.log(level, message, *args)


def _cuda_device_name() -> Optional[str]:
    """Human-readable name of the current CUDA device, or None. Never raises."""
    if not cuda_available():
        return None
    try:
        import torch

        return torch.cuda.get_device_name(0)
    except Exception:
        return None


def _torch_version() -> Optional[str]:
    if not torch_available():
        return None
    try:
        import torch

        return str(torch.__version__)
    except Exception:
        return None


def _cuda_device_count() -> Optional[int]:
    if not cuda_available():
        return 0
    try:
        import torch

        return int(torch.cuda.device_count())
    except Exception:
        return None


def resolve_device(requested: Optional[str] = None) -> str:
    """
    Turn a requested device string into a concrete one.

    Args:
        requested: ``auto`` | ``cpu`` | ``cuda`` | ``cuda:N``.
                   None means "use settings.device".

    Returns:
        "cpu", "cuda" or "cuda:N".

    Raises:
        DeviceUnavailableError: an explicit cuda request cannot be satisfied.
                                Never raised for "auto" -- that is the only
                                difference between "auto" and "cuda".
        ValueError: the string is not an accepted device.
    """
    if requested is None:
        from shared.config import get_settings

        requested = get_settings().device

    value = (requested or "").strip().lower()

    if value == "auto":
        if cuda_available():
            resolved = CUDA
            _log_once(
                "auto:cuda",
                logging.INFO,
                "device=cuda (auto: %s)",
                _cuda_device_name() or "unnamed CUDA device",
            )
        else:
            resolved = CPU
            _log_once(
                "auto:cpu",
                logging.INFO,
                "device=cpu (auto: torch.cuda unavailable, torch installed: %s)",
                "yes" if torch_available() else "no",
            )
        return resolved

    if value == CPU:
        _log_once("cpu", logging.INFO, "device=cpu (requested: cpu)")
        return CPU

    if value == CUDA or value.startswith("cuda:"):
        if not cuda_available():
            raise DeviceUnavailableError(
                f"DEVICE={value} was requested but torch reports no usable CUDA "
                f"device (torch installed: {'yes' if torch_available() else 'no'}). "
                "Install the CUDA build "
                "(pip install -r backend/requirements-cuda.txt) or set DEVICE=auto."
            )
        if value.startswith("cuda:"):
            index = int(value.split(":", 1)[1])
            count = _cuda_device_count()
            if count is not None and index >= count:
                raise DeviceUnavailableError(
                    f"DEVICE={value} was requested but torch reports only "
                    f"{count} CUDA device(s) (valid indices 0..{max(count - 1, 0)}). "
                    "Set DEVICE=cuda to use the default device, or DEVICE=auto."
                )
        _log_once(
            f"explicit:{value}",
            logging.INFO,
            "device=%s (requested: %s, %s)",
            value,
            value,
            _cuda_device_name() or "unnamed CUDA device",
        )
        return value

    raise ValueError(
        f"DEVICE={requested!r} is not a valid device. Accepted values: "
        "'auto' (CUDA when available, otherwise CPU), 'cpu', 'cuda', "
        "or 'cuda:N' for a specific GPU index."
    )


def resolve_dtype_name(device: str, requested: Optional[str] = None) -> str:
    """
    Resolve the torch dtype to use, as a NAME.

    Callers map the name to a real torch dtype inside their own torch-guarded
    code, so config and this module never carry a torch object.

    ``auto`` means float16 on cuda and float32 on cpu: float16 on CPU is slow
    and numerically unstable for Florence-2.
    """
    if requested is None:
        from shared.config import get_settings

        requested = get_settings().vision_torch_dtype

    value = (requested or "auto").strip().lower()

    if value == "auto":
        return "float16" if device.startswith(CUDA) else "float32"

    if value not in {"float32", "float16", "bfloat16"}:
        raise ValueError(
            f"VISION_TORCH_DTYPE={requested!r} is not valid. Accepted values: "
            "auto, float32, float16, bfloat16."
        )

    return value


def resolve_whisper_device() -> str:
    """
    Device for audio transcription: WHISPER_DEVICE if set, otherwise DEVICE.

    A non-empty WHISPER_DEVICE is a per-component override that wins over
    DEVICE (config.py logs a WARNING saying so on every boot), so an existing
    .env keeps its exact current behaviour.

    Then a capability gate: faster-whisper runs on CTranslate2, which links its
    own cuDNN. In the current image a CUDA run dies with the opaque
    ``Unable to load libcudnn_ops.so.9``. A logged CPU fallback beats a 500 on
    every transcription.
    """
    from shared.config import get_settings

    settings = get_settings()
    requested = settings.whisper_device or settings.device
    device = resolve_device(requested)

    if not device.startswith(CUDA):
        return device

    try:
        import ctranslate2

        usable = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        usable = False

    if not usable:
        _log_once(
            "whisper:ct2-fallback",
            logging.WARNING,
            "audio: falling back to cpu - ctranslate2 reports no CUDA device "
            "(the CUDA build ships nvidia-cudnn-cu12; see "
            "backend/requirements-cuda.txt) [requested=%s, resolved=%s]",
            requested,
            device,
        )
        return CPU

    return device


def resolve_whisper_compute_type(device: str) -> str:
    """
    CTranslate2 compute type for the resolved audio device.

    WHISPER_COMPUTE_TYPE wins when set; otherwise float16 on cuda, int8 on cpu.
    Deriving it closes the trap where flipping only the device leaves
    CTranslate2 on a CPU-shaped int8 quantisation, which it silently downgrades
    rather than rejecting.
    """
    from shared.config import get_settings

    configured = (get_settings().whisper_compute_type or "").strip()
    if configured:
        return configured

    return "float16" if device.startswith(CUDA) else "int8"


def resolve_docling_device() -> str:
    """
    Device for Docling. A thin alias of resolve_device().

    It exists so converter.py has one obvious call and so this note lives in
    one place: the value is passed explicitly into
    ``AcceleratorOptions(device=...)``, and a pydantic-settings init kwarg
    outranks the environment, so **DOCLING_DEVICE is from now on IGNORED**.
    Use DEVICE instead.

    Docling's own default is ``device="auto"``, which resolves to ``cuda:0``
    whenever a GPU is visible -- across every worker process, each with its own
    CUDA context and layout/table weights, and with nothing logged. Making the
    decision here makes it ours and visible.
    """
    return resolve_device()


def device_report() -> Dict[str, Any]:
    """
    Everything an operator needs to explain the current device choice.

    Backs GET /images/capabilities, so it never raises: on failure it reports
    ``resolved="cpu"`` with ``reason`` set to the exception text.
    """
    from shared.config import get_settings

    try:
        requested = get_settings().device
    except Exception as exc:
        requested = "auto"
        return {
            "requested": requested,
            "resolved": CPU,
            "torch_available": False,
            "cuda_available": False,
            "torch_version": None,
            "cuda_device_name": None,
            "reason": str(exc),
        }

    reason: Optional[str] = None
    try:
        resolved = resolve_device(requested)
    except Exception as exc:
        resolved = CPU
        reason = str(exc)

    if reason is None:
        if requested == "auto":
            reason = (
                f"auto: {_cuda_device_name() or 'CUDA device'} detected"
                if resolved.startswith(CUDA)
                else "auto: torch.cuda unavailable"
            )
        else:
            reason = f"explicitly requested: {requested}"

    return {
        "requested": requested,
        "resolved": resolved,
        "torch_available": torch_available(),
        "cuda_available": cuda_available(),
        "torch_version": _torch_version(),
        "cuda_device_name": _cuda_device_name(),
        "reason": reason,
    }
