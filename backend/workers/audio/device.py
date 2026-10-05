"""
Device selection for local Whisper models (GPU vs CPU)

Detection runs once per worker process and the result is cached in a module
variable, so jobs never pay for it again. If the GPU later fails (e.g. CUDA
libraries missing when the model loads or runs), mark_gpu_unavailable()
switches the cache to CPU permanently for this process, so the failure is
not retried on every job.

The device itself is decided by shared.device.resolve_whisper_device()
(WHISPER_DEVICE, else DEVICE; see docs/GPU.md). An explicit cuda still falls
back to CPU here if the model then fails to load or run on the GPU.
"""

import logging
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# CTranslate2 (faster-whisper) cannot run float16 on CPU; int8 is the fast CPU option
CPU_COMPUTE_TYPE = "int8"
GPU_COMPUTE_TYPE = "float16"


@dataclass(frozen=True)
class WhisperDevice:
    device: str  # "cuda" or "cpu"
    compute_type: str  # e.g. "float16", "int8"
    reason: str  # why this device was chosen (for logs / job metadata)


_device: Optional[WhisperDevice] = None
_lock = threading.Lock()


def get_whisper_device() -> WhisperDevice:
    """Return the device to run Whisper on, detecting it only on the first call"""
    global _device
    if _device is None:
        with _lock:
            if _device is None:
                _device = _detect_device()
                logger.info(
                    f"Whisper device selected: {_device.device} "
                    f"(compute_type={_device.compute_type}, reason={_device.reason})"
                )
    return _device


def mark_gpu_unavailable(reason: str) -> WhisperDevice:
    """Record that the GPU failed and switch this process to CPU for good"""
    global _device
    with _lock:
        _device = WhisperDevice(device="cpu", compute_type=CPU_COMPUTE_TYPE, reason=f"gpu fallback: {reason}")
    logger.warning(f"GPU disabled for Whisper in this worker, using CPU from now on: {reason}")
    return _device


def reset_whisper_device() -> None:
    """Forget the cached device (tests, or after changing configuration)"""
    global _device
    with _lock:
        _device = None


def is_gpu_error(error: BaseException) -> bool:
    """Heuristic: does this exception come from CUDA / GPU libraries?"""
    message = f"{type(error).__name__}: {error}".lower()
    return any(token in message for token in ("cuda", "cudnn", "cublas", "gpu", "nvidia", "libcu"))


def _detect_device() -> WhisperDevice:
    """
    The one-time decision, delegated to shared.device so audio follows the same
    rules as everything else: WHISPER_DEVICE (or DEVICE when it is empty), and
    the CTranslate2 cuDNN gate that falls back to CPU before a model load would
    die with `Unable to load libcudnn_ops.so.9`. This module only adds the
    per-process cache and the runtime fallback on top.
    """
    from shared.config import get_settings
    from shared.device import resolve_whisper_compute_type, resolve_whisper_device

    settings = get_settings()
    requested = (settings.whisper_device or settings.device or "auto").strip().lower()

    device = resolve_whisper_device()
    compute_type = resolve_whisper_compute_type(device)

    if requested == "auto":
        reason = f"auto: {'CUDA device found' if device.startswith('cuda') else 'no usable CUDA device'}"
    elif device.split(":")[0] != requested.split(":")[0]:
        reason = f"requested {requested}, not usable here"
    else:
        reason = "configured"

    return WhisperDevice(device=device, compute_type=compute_type, reason=reason)
