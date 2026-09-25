"""
Device selection for local Whisper models (GPU vs CPU)

Detection runs once per worker process and the result is cached in a module
variable, so jobs never pay for it again. If the GPU later fails (e.g. CUDA
libraries missing when the model loads or runs), mark_gpu_unavailable()
switches the cache to CPU permanently for this process, so the failure is
not retried on every job.

Configuration (WHISPER_DEVICE / WHISPER_COMPUTE_TYPE):
- WHISPER_DEVICE=auto (default): use CUDA when a GPU is available, else CPU
- WHISPER_DEVICE=cuda or cpu: force a device (cuda still falls back on failure)
- WHISPER_COMPUTE_TYPE=auto (default): float16 on GPU, int8 on CPU
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
    from shared.config import get_settings
    settings = get_settings()

    requested = (settings.whisper_device or "auto").strip().lower()
    requested_compute = (settings.whisper_compute_type or "auto").strip().lower()

    if requested == "cpu":
        device, reason = "cpu", "configured"
    elif requested == "cuda":
        device, reason = "cuda", "configured"
    else:
        gpu_count = _cuda_device_count()
        if gpu_count > 0:
            device, reason = "cuda", f"auto: {gpu_count} CUDA device(s) found"
        else:
            device, reason = "cpu", "auto: no CUDA device found"

    if requested_compute != "auto":
        compute_type = requested_compute
    else:
        compute_type = GPU_COMPUTE_TYPE if device == "cuda" else CPU_COMPUTE_TYPE

    return WhisperDevice(device=device, compute_type=compute_type, reason=reason)


def _cuda_device_count() -> int:
    """Count usable CUDA devices without failing when no GPU stack is installed"""
    # faster-whisper runs on CTranslate2, whose check does not need PyTorch
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception as e:
        logger.debug(f"CTranslate2 CUDA check unavailable: {e}")

    # openai-whisper runs on PyTorch
    try:
        import torch
        return torch.cuda.device_count() if torch.cuda.is_available() else 0
    except Exception as e:
        logger.debug(f"PyTorch CUDA check unavailable: {e}")

    return 0
