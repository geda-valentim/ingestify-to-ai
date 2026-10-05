"""
Deterministic stub describer.

This is the seam that keeps ``pytest backend/tests/`` free of torch and
transformers: ``backend/tests/conftest.py`` sets ``VISION_PROVIDER=stub``, so
the factory hands every test this class instead of Florence-2. It also gives an
operator a way to exercise the endpoints, the queue and the job lifecycle on a
machine that cannot run the model at all.

Output is derived from the image dimensions so it is deterministic and obviously
synthetic - nothing here should ever be mistaken for a real caption.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from workers.vision.base_describer import ImageDescriber

logger = logging.getLogger(__name__)

STUB_MODEL_ID = "stub"
STUB_REVISION = "stub"


class StubDescriber(ImageDescriber):
    """A zero-dependency ImageDescriber with fixed, dimension-derived output."""

    def __init__(self, task: str = "<MORE_DETAILED_CAPTION>") -> None:
        self._task = task
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self._loaded = True

    def info(self) -> Dict[str, Any]:
        return {
            "model_id": STUB_MODEL_ID,
            "revision": STUB_REVISION,
            "device": "cpu",
            "dtype": "float32",
            "loaded": self._loaded,
        }

    def describe(
        self, image_path: Path, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        self.load()
        options = options or {}
        task = options.get("task") or self._task
        width, height = self._dimensions(Path(image_path))
        return {
            "description": f"A stub description of a {width}x{height} image.",
            "task": task,
            "width": width,
            "height": height,
            "duration_ms": 0,
        }

    def ocr(
        self, image_path: Path, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        self.load()
        width, height = self._dimensions(Path(image_path))
        lines = [
            {
                "text": "stub line one",
                "quad_box": [0.0, 0.0, float(width), 0.0, float(width), 10.0, 0.0, 10.0],
                "bbox": [0.0, 0.0, float(width), 10.0],
            },
            {
                "text": "stub line two",
                "quad_box": [
                    0.0, 20.0, float(width), 20.0, float(width), 30.0, 0.0, 30.0,
                ],
                "bbox": [0.0, 20.0, float(width), 30.0],
            },
        ]
        return {
            "text": "\n".join(line["text"] for line in lines),
            "lines": lines,
            "width": width,
            "height": height,
            "duration_ms": 0,
        }

    @staticmethod
    def _dimensions(image_path: Path) -> tuple:
        """Read the real dimensions when PIL is around, else a fixed placeholder.

        PIL must stay optional here - the stub's whole purpose is running where
        the vision extra is not installed.
        """
        try:
            from PIL import Image
        except ImportError:
            return (1, 1)

        try:
            with Image.open(image_path) as image:
                return image.size
        except Exception as exc:  # pragma: no cover - stub is best-effort
            logger.debug("stub describer could not size %s: %s", image_path, exc)
            return (1, 1)
