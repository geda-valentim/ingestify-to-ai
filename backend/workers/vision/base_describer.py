"""
Abstract base class for image description / OCR providers.

Mirrors ``workers/audio/base_transcriber.py``: one interface, several
implementations, chosen by configuration. The contract deliberately keeps
``load()`` separate from ``describe()``/``ocr()`` so a warmup hook can pay the
model-load cost at worker start instead of inside a request that a caller is
holding a connection open for.

Implementations must not import torch, transformers or PIL at module import
time - only inside ``load()``. That is what lets ``celery_app`` import the
vision tasks in every process (API, beat, general worker) at zero cost.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional


class ImageDescriber(ABC):
    """Interface every vision provider implements."""

    def analyze(self, image_path: Path, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run a task from the provider's advertised vocabulary."""
        from workers.vision.errors import VisionUnsupportedTaskError
        raise VisionUnsupportedTaskError("This provider does not support general image analysis")

    @abstractmethod
    def describe(
        self, image_path: Path, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Caption an image.

        Args:
            image_path: Path to the image on local disk.
            options: Optional overrides. Recognised key:
                - task (str): Florence-2 task prompt, one of
                  ``<CAPTION>``, ``<DETAILED_CAPTION>``, ``<MORE_DETAILED_CAPTION>``.

        Returns:
            {
                "description": str,
                "task": str,
                "width": int,
                "height": int,
                "duration_ms": int,
            }

        Raises:
            VisionError: Any typed failure (dependencies, weights, inference).
        """

    @abstractmethod
    def ocr(
        self, image_path: Path, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Read text out of an image, with per-line regions.

        Returns:
            {
                "text": str,           # lines joined with "\\n", emission order
                "lines": [
                    {
                        "text": str,
                        "quad_box": [x1, y1, x2, y2, x3, y3, x4, y4],
                        "bbox": [x_min, y_min, x_max, y_max],
                    },
                    ...
                ],
                "width": int,
                "height": int,
                "duration_ms": int,
            }

            Coordinates are absolute pixels in the ORIGINAL image size and are
            floats, not ints - tightening the type at the serialization
            boundary would only turn a data surprise into a 500.

            An image with no detectable text is a success with ``text == ""``
            and ``lines == []``, never an error.

        Raises:
            VisionError: Any typed failure.
        """

    @abstractmethod
    def info(self) -> Dict[str, Any]:
        """Describe the configured model without loading it.

        Returns:
            {"model_id": str, "revision": str, "device": str,
             "dtype": str, "loaded": bool}
        """

    @abstractmethod
    def load(self) -> None:
        """Load the model. Idempotent, and safe to call from a warmup hook."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """True once weights are resident in this process."""
