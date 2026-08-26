"""
Florence-2 image description and OCR.

One model serves both operations: ``describe()`` runs a caption task prompt,
``ocr()`` runs ``<OCR_WITH_REGION>``. That single load path is the reason the
two endpoints share one feature flag - there is no state in which one is
available and the other is not.

Import safety is a hard requirement, not a nicety. Nothing in this module
imports torch, transformers or PIL at module or constructor level; the whole
class is strings until ``load()`` is called. ``workers/celery_app.py`` imports
the vision tasks in *every* process - the API, beat, and the general worker -
and none of them should pay for a torch import they will never use.

The default model (``florence-community/Florence-2-base-ft``) is a weights-only
conversion: safetensors and configs, no ``.py`` files, no ``custom_code`` tag.
It loads through the transformers-native ``Florence2ForConditionalGeneration``
(4.56+), which is precisely what makes ``trust_remote_code`` unnecessary. The
open-source default therefore executes no code downloaded from the Hub.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from workers.vision.base_describer import ImageDescriber
from workers.vision.errors import (
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

logger = logging.getLogger(__name__)

# The only caption prompts a caller may select. The request schema is a Literal
# over exactly these, and this set is the second line of defence: `task` reaches
# the worker as a plain string over the broker, and an arbitrary caller-supplied
# prompt must never reach the model.
CAPTION_TASKS = ("<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>")

# Fixed, not a caller choice: region-annotated OCR is the whole point of /images/ocr.
OCR_TASK = "<OCR_WITH_REGION>"

_TORCH_DTYPES = ("float32", "float16", "bfloat16")

# Florence-2 emits this in front of decoded labels; it is an artefact of
# decoding with skip_special_tokens=False, which post_process_generation needs.
_EOS = "</s>"


class _Florence2Backend:
    """The heavy modules, imported once and passed around explicitly.

    Holding them on an object rather than importing at module scope is what
    makes the describer injectable: tests replace ``_import_backend()`` with
    one returning fakes, and never import torch at all.
    """

    __slots__ = ("torch", "image_module", "auto_processor", "model_cls")

    def __init__(self, torch, image_module, auto_processor, model_cls):
        self.torch = torch
        self.image_module = image_module
        self.auto_processor = auto_processor
        self.model_cls = model_cls


class Florence2Describer(ImageDescriber):
    """Caption and OCR an image with Florence-2."""

    def __init__(
        self,
        model_id: str,
        revision: str,
        device: str,
        dtype: str,
        cache_dir: str,
        trust_remote_code: bool = False,
        allow_download: bool = True,
        max_new_tokens: int = 1024,
        num_beams: int = 3,
        max_image_pixels: int = 50_000_000,
    ) -> None:
        # Stores strings and touches nothing else. No torch, no transformers,
        # no PIL at construction - see the module docstring.
        self.model_id = model_id
        self.revision = revision
        self.device = device
        self.dtype = dtype
        self.cache_dir = cache_dir
        self.trust_remote_code = trust_remote_code
        self.allow_download = allow_download
        self.max_new_tokens = max_new_tokens
        self.num_beams = num_beams
        self.max_image_pixels = max_image_pixels

        self._backend: Optional[_Florence2Backend] = None
        self._processor = None
        self._model = None
        self._torch_dtype = None
        self._resolved_dtype_name: Optional[str] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._model is not None and self._processor is not None

    def info(self) -> Dict[str, Any]:
        """Report the configuration without loading anything."""
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "device": self.device,
            "dtype": self._resolved_dtype_name or self.dtype,
            "loaded": self.is_loaded,
        }

    def _import_backend(self) -> _Florence2Backend:
        """Import the heavy dependencies.

        This is the single seam through which torch enters the process, which
        makes it the single place tests need to replace. Overriding it on an
        instance yields a fully exercised describer with no torch installed.
        """
        try:
            import torch
            from PIL import Image
            from transformers import AutoProcessor, Florence2ForConditionalGeneration
        except ImportError as exc:
            # Importing Florence2ForConditionalGeneration by name doubles as the
            # transformers version check: it is native from 4.56 onward, so on an
            # older release this is the ImportError the user sees.
            if "Florence2" in str(exc):
                raise VisionDependenciesMissingError(
                    "This transformers release has no native "
                    "Florence2ForConditionalGeneration (added in 4.56). Upgrade with: "
                    "pip install -r backend/requirements-vision.txt (CPU) or "
                    "backend/requirements-vision-cuda.txt (NVIDIA GPU)."
                ) from exc
            raise VisionDependenciesMissingError.default(exc) from exc

        return _Florence2Backend(
            torch=torch,
            image_module=Image,
            auto_processor=AutoProcessor,
            model_cls=Florence2ForConditionalGeneration,
        )

    def _resolve_dtype_name(self) -> str:
        """Turn the configured dtype into a concrete name.

        Device-to-dtype policy lives in ``shared.device`` and nowhere else; this
        only reaches for it when the value is still ``auto``.
        """
        requested = (self.dtype or "auto").strip().lower()
        if requested in _TORCH_DTYPES:
            return requested
        if requested == "auto":
            from shared.device import resolve_dtype_name

            return resolve_dtype_name(self.device, "auto")
        raise ValueError(
            f"Unsupported VISION_TORCH_DTYPE '{self.dtype}'. "
            f"Accepted values: auto, {', '.join(_TORCH_DTYPES)}."
        )

    def load(self) -> None:
        """Load processor and weights. Idempotent and thread-safe."""
        if self.is_loaded:
            return

        with self._lock:
            # Re-check: another thread may have loaded while we waited.
            if self.is_loaded:
                return

            backend = self._backend or self._import_backend()
            dtype_name = self._resolve_dtype_name()
            torch_dtype = getattr(backend.torch, dtype_name)

            if self.trust_remote_code:
                logger.warning(
                    "vision_trust_remote_code=True - executing model code from "
                    "%s@%s inside this worker process",
                    self.model_id,
                    self.revision,
                )

            # revision= goes to BOTH calls. The processor is a separate download,
            # and an unpinned processor is an unpinned artefact.
            common = {
                "revision": self.revision,
                "cache_dir": self.cache_dir,
                "trust_remote_code": self.trust_remote_code,
                "local_files_only": not self.allow_download,
            }

            started = time.perf_counter()
            try:
                processor = backend.auto_processor.from_pretrained(self.model_id, **common)
                model = backend.model_cls.from_pretrained(
                    self.model_id, dtype=torch_dtype, **common
                )
                model = model.to(self.device).eval()
            except Exception as exc:
                raise self._map_load_failure(exc) from exc

            duration_ms = int((time.perf_counter() - started) * 1000)

            self._backend = backend
            self._processor = processor
            self._model = model
            self._torch_dtype = torch_dtype
            self._resolved_dtype_name = dtype_name

            logger.info(
                "vision: loaded %s@%s device=%s dtype=%s in %dms",
                self.model_id,
                self.revision[:8],
                self.device,
                dtype_name,
                duration_ms,
            )

    def _map_load_failure(self, exc: Exception) -> Exception:
        """Turn a load failure into the typed error that says what to do next."""
        if isinstance(exc, VisionError):
            return exc

        name = type(exc).__name__
        message = str(exc)

        # Weights absent from the cache while downloading is switched off. The
        # hub raises several different classes for this; all of them are OSError
        # subclasses, and the operator's next step is the same for each.
        not_downloaded = name in {
            "LocalEntryNotFoundError",
            "EntryNotFoundError",
            "RepositoryNotFoundError",
            "OfflineModeIsEnabled",
        }
        if not self.allow_download and (not_downloaded or isinstance(exc, OSError)):
            return VisionModelNotDownloadedError.for_model(
                self.model_id, self.revision, self.cache_dir
            )

        if self.device.startswith("cuda") and (
            "CUDA" in message or "cuda" in message or "device" in message.lower()
        ):
            return VisionDeviceUnavailableError(
                f"Could not place {self.model_id} on device '{self.device}': {message}. "
                "Set DEVICE=auto to fall back to CPU, or install the CUDA build "
                "(pip install -r backend/requirements-cuda.txt)."
            )

        return VisionModelLoadError(
            f"Failed to load {self.model_id}@{self.revision} from cache "
            f"{self.cache_dir}: {name}: {message}"
        )

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def describe(
        self, image_path: Path, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        options = options or {}
        task = options.get("task") or self._default_caption_task()
        if task not in CAPTION_TASKS:
            raise VisionUnsupportedTaskError(
                f"Unsupported caption task '{task}'. "
                f"Accepted values: {', '.join(CAPTION_TASKS)}."
            )

        parsed, width, height, duration_ms = self._generate(image_path, task)

        raw = parsed.get(task) if isinstance(parsed, dict) else parsed
        if raw is None:
            description = ""
        elif isinstance(raw, str):
            description = raw
        else:
            # Defensive: post_process_generation's return shape is exactly the
            # sort of detail that shifts across a transformers major version.
            description = str(raw)

        return {
            "description": _clean_text(description),
            "task": task,
            "width": width,
            "height": height,
            "duration_ms": duration_ms,
        }

    def ocr(
        self, image_path: Path, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        parsed, width, height, duration_ms = self._generate(image_path, OCR_TASK)

        region = parsed.get(OCR_TASK) if isinstance(parsed, dict) else None
        region = region if isinstance(region, dict) else {}
        quad_boxes = region.get("quad_boxes") or []
        labels = region.get("labels") or []

        # zip() drops an unpaired tail on either side. That is deliberate: a
        # shape change upstream should cost us a line, not the whole request.
        if len(labels) != len(quad_boxes):
            logger.warning(
                "vision ocr: %d labels but %d quad_boxes - dropping the unpaired tail",
                len(labels),
                len(quad_boxes),
            )

        lines: List[Dict[str, Any]] = []
        for label, quad in zip(labels, quad_boxes):
            lines.append(
                {
                    "text": _clean_text(label),
                    **_coordinates(quad),
                }
            )

        return {
            # Emission order, not reading order: re-sorting would be an
            # invented behaviour, not a faithful report of what the model said.
            "text": "\n".join(line["text"] for line in lines),
            "lines": lines,
            "width": width,
            "height": height,
            "duration_ms": duration_ms,
        }

    def _default_caption_task(self) -> str:
        from shared.config import get_settings

        return get_settings().vision_caption_task

    def _generate(self, image_path: Path, task_prompt: str):
        """Run one generation pass and return (parsed, width, height, duration_ms)."""
        self.load()
        backend = self._backend

        image, width, height = self._open_image(Path(image_path), backend)

        started = time.perf_counter()
        try:
            inputs = self._processor(
                text=task_prompt, images=image, return_tensors="pt"
            ).to(self.device, self._torch_dtype)

            # inference_mode() is mandatory, not an optimisation: without it every
            # request retains an autograd graph and the resident footprint grows.
            with backend.torch.inference_mode():
                generated_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    num_beams=self.num_beams,
                    do_sample=False,
                )

            generated_text = self._processor.batch_decode(
                generated_ids, skip_special_tokens=False
            )[0]

            # image_size is what makes the returned coordinates absolute pixels
            # in the ORIGINAL image rather than in Florence-2's 1000x1000 grid.
            parsed = self._processor.post_process_generation(
                generated_text, task=task_prompt, image_size=(width, height)
            )
        except VisionError as exc:
            raise exc
        except Exception as exc:
            raise VisionInferenceError(
                f"Florence-2 inference failed for task {task_prompt} on a "
                f"{width}x{height} image: {type(exc).__name__}: {exc}"
            ) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        return parsed, width, height, duration_ms

    def _open_image(self, path: Path, backend: _Florence2Backend):
        """Open and validate the image, guarding against decompression bombs."""
        if not path.exists():
            raise VisionInferenceError(
                f"Image file not found at {path}. The API writes the image under "
                "temp_storage_path and the worker reads it back, so this usually "
                "means ./tmp:/tmp/ingestify is not mounted in both containers."
            )

        image_module = backend.image_module
        # A byte-size limit does not protect this process: a 10MB PNG can expand
        # to tens of gigabytes of pixels. Both PIL's own guard and an explicit
        # re-check are used, because the two catch it at different moments.
        image_module.MAX_IMAGE_PIXELS = self.max_image_pixels

        try:
            with image_module.open(path) as opened:
                width, height = opened.size
                if width * height > self.max_image_pixels:
                    raise VisionImageTooLargeError(
                        f"Image is {width}x{height} = {width * height} pixels, over the "
                        f"{self.max_image_pixels} limit (VISION_MAX_IMAGE_PIXELS)."
                    )
                image = opened.convert("RGB")
        except VisionError as exc:
            raise exc
        except Exception as exc:
            if "DecompressionBomb" in type(exc).__name__:
                raise VisionImageTooLargeError(
                    f"Image exceeds the {self.max_image_pixels} pixel limit "
                    "(VISION_MAX_IMAGE_PIXELS)."
                ) from exc
            raise VisionInvalidImageError(
                f"Could not decode the image at {path}: {type(exc).__name__}: {exc}"
            ) from exc

        return image, width, height


def _clean_text(value: Any) -> str:
    """Strip Florence-2's decoded end-of-sequence marker and surrounding space."""
    text = value if isinstance(value, str) else ("" if value is None else str(value))
    return text.strip().removeprefix(_EOS).strip()


def _coordinates(quad: Any) -> Dict[str, List[float]]:
    """Turn one quad box into its rounded quad plus a derived axis-aligned bbox.

    Coordinates stay floats. Tightening the type here would only convert a data
    surprise into a 500 at the serialization boundary.
    """
    try:
        coords = [round(float(value), 2) for value in quad]
    except (TypeError, ValueError):
        logger.warning("vision ocr: unreadable quad_box %r - reporting the text only", quad)
        return {"quad_box": [], "bbox": []}

    xs = coords[0::2]
    ys = coords[1::2]
    if not xs or not ys:
        return {"quad_box": coords, "bbox": []}

    return {
        "quad_box": coords,
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
    }
