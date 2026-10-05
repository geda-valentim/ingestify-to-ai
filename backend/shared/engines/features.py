"""
The features an engine can run, and what each costs in GPU memory.

A feature is a kind of heavy work with its own local lane (the Celery queue and
compose service that run it today). VRAM footprints are per process, CUDA
context included (spec 0003, Appendix G); a benchmark measurement or a per-binding
override replaces them.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Feature:
    name: str
    title: str
    vram_per_execution_gb: float
    local_service: str  # compose service of the local lane
    local_queue_setting: str  # Settings attribute holding its Celery queue
    scale_hint: str  # how an operator changes the number of local replicas


TRANSCRIPTION = Feature(
    "transcription", "Transcription (Whisper)", 3.0, "worker-audio", "transcription_queue",
    "AUDIO_WORKER_REPLICAS={workers} docker compose up -d worker-audio",
)
DOCUMENT_CONVERSION = Feature(
    "document_conversion", "Document conversion (Docling)", 1.5, "worker", "celery_task_default_queue",
    "docker compose up -d --scale worker={workers} worker",
)
VISION = Feature(
    "vision", "Vision (Florence-2)", 1.8, "worker-vision", "vision_queue",
    "docker compose up -d --scale worker-vision={workers} worker-vision",
)

FEATURES: Dict[str, Feature] = {f.name: f for f in (TRANSCRIPTION, DOCUMENT_CONVERSION, VISION)}

# Florence-2-large needs about twice the base model (docs/GPU.md)
VISION_LARGE_VRAM_GB = 3.8


def get_feature(name: str) -> Feature:
    try:
        return FEATURES[name]
    except KeyError:
        raise ValueError(f"Unknown feature {name!r}; expected one of {', '.join(FEATURES)}") from None


def default_vram_gb(feature: str, vision_model_id: Optional[str] = None) -> float:
    """Default footprint of one execution of a feature, CUDA context included"""
    if feature == VISION.name and vision_model_id and "large" in vision_model_id.lower():
        return VISION_LARGE_VRAM_GB
    return get_feature(feature).vram_per_execution_gb


def feature_for_queue(queue: str, settings) -> Optional[str]:
    """The feature whose local lane is this Celery queue (None for other queues)"""
    for feature in FEATURES.values():
        if getattr(settings, feature.local_queue_setting, None) == queue:
            return feature.name
    return None
