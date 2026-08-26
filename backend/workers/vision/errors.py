"""
Typed vision failures.

Every failure a caller can act on gets a class here, carrying the HTTP status
and the machine-readable ``error_code`` the API surfaces. The point is that a
worker-side failure survives Celery's JSON result serializer with its meaning
intact: the tasks in ``workers/vision_tasks.py`` catch ``VisionError`` and
*return* ``{"ok": False, "error_code": ..., "http_status": ..., "detail": ...}``
instead of raising, so the API can map it faithfully rather than turning every
model problem into an opaque 500.

Messages are written to tell the operator what to do next, not merely what
broke - these are the strings a first-time open-source user will read.
"""


class VisionError(Exception):
    """Base class for every failure the vision pipeline can report."""

    error_code: str = "VISION_ERROR"
    http_status: int = 500


class VisionDependenciesMissingError(VisionError):
    """torch / transformers / Pillow are not installed in this process."""

    error_code = "VISION_DEPENDENCIES_MISSING"
    http_status = 503

    @classmethod
    def default(cls, cause: object = None) -> "VisionDependenciesMissingError":
        message = (
            "Florence-2 support is not installed. Install the vision extra: "
            "pip install -r backend/requirements-vision.txt (CPU) or "
            "backend/requirements-vision-cuda.txt (NVIDIA GPU)."
        )
        if cause is not None:
            message = f"{message} (import failed: {cause})"
        return cls(message)


class VisionModelNotDownloadedError(VisionError):
    """Weights are absent from the cache and downloading them is disabled."""

    error_code = "VISION_MODEL_NOT_DOWNLOADED"
    http_status = 503

    @classmethod
    def for_model(
        cls, model_id: str, revision: str, cache_dir: str
    ) -> "VisionModelNotDownloadedError":
        return cls(
            f"Model {model_id}@{revision} is not in the cache at {cache_dir} "
            "and VISION_ALLOW_MODEL_DOWNLOAD=false. "
            "Prefetch it with: make vision-download"
        )


class VisionModelLoadError(VisionError):
    """The weights exist but could not be loaded (corrupt cache, OOM, bad dtype)."""

    error_code = "VISION_MODEL_LOAD_FAILED"
    http_status = 503


class VisionDeviceUnavailableError(VisionError):
    """An explicitly requested device could not be provided."""

    error_code = "VISION_DEVICE_UNAVAILABLE"
    http_status = 503


class VisionImageTooLargeError(VisionError):
    """The decoded image exceeds vision_max_image_pixels.

    Separate from the byte-size limit the API enforces: a 10MB PNG can expand
    to tens of gigabytes of pixels, so the byte limit alone does not protect
    the worker. Checked again here because this is the process that would die.
    """

    error_code = "IMAGE_TOO_LARGE"
    http_status = 422


class ImagePayloadTooLargeError(VisionError):
    """The encoded/uploaded image exceeds vision_max_image_size_mb.

    Distinct from VisionImageTooLargeError: this is a byte-count limit and
    answers 413, while the pixel-count limit answers 422. They deliberately
    share the IMAGE_TOO_LARGE code, because to a caller they are one concern.
    """

    error_code = "IMAGE_TOO_LARGE"
    http_status = 413


class InvalidImageBase64Error(VisionError):
    """The image_base64 field is not decodable base64."""

    error_code = "INVALID_BASE64"
    http_status = 422


class VisionInvalidImageError(VisionError):
    """The bytes are not a decodable image in a format we accept."""

    error_code = "UNSUPPORTED_IMAGE_FORMAT"
    http_status = 422


class VisionUnsupportedTaskError(VisionError):
    """A caption task prompt outside the allowed set reached the worker.

    Unreachable through the HTTP schema (a Literal over three values); this is
    the worker-side guard, since `task` arrives as a plain string over the
    broker and an arbitrary prompt must never reach the model.
    """

    error_code = "UNSUPPORTED_TASK"
    http_status = 422


class VisionInferenceError(VisionError):
    """Generation itself failed after the model was loaded."""

    error_code = "VISION_INFERENCE_FAILED"
    http_status = 500


__all__ = [
    "VisionError",
    "VisionDependenciesMissingError",
    "VisionModelNotDownloadedError",
    "VisionModelLoadError",
    "VisionDeviceUnavailableError",
    "VisionImageTooLargeError",
    "VisionInvalidImageError",
    "ImagePayloadTooLargeError",
    "InvalidImageBase64Error",
    "VisionUnsupportedTaskError",
    "VisionInferenceError",
]
