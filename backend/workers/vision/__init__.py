"""
Image description and OCR (Florence-2).

Importing this package is free: no torch, no transformers, no PIL, and no
network access happens until a describer's ``load()`` is called. That property
is load-bearing - ``workers/celery_app.py`` imports the vision tasks in every
process, including the API and beat, and the test suite runs with none of those
libraries installed.
"""

from workers.vision.base_describer import ImageDescriber
from workers.vision.errors import (
    ImagePayloadTooLargeError,
    InvalidImageBase64Error,
    VisionDependenciesMissingError,
    VisionDeviceUnavailableError,
    VisionError,
    VisionImageTooLargeError,
    VisionInferenceError,
    VisionInvalidImageError,
    VisionModelLoadError,
    VisionModelNotDownloadedError,
    VisionUnsupportedTaskError,
)
from workers.vision.factory import (
    get_available_providers,
    get_image_describer,
    reset_image_describer,
)

__all__ = [
    "ImageDescriber",
    "get_image_describer",
    "reset_image_describer",
    "get_available_providers",
    "VisionError",
    "VisionDependenciesMissingError",
    "VisionModelNotDownloadedError",
    "VisionModelLoadError",
    "VisionDeviceUnavailableError",
    "VisionImageTooLargeError",
    "VisionInvalidImageError",
    "VisionUnsupportedTaskError",
    "VisionInferenceError",
    "ImagePayloadTooLargeError",
    "InvalidImageBase64Error",
]
