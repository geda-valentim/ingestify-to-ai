"""
Local worker heartbeats (spec 0003, 4.6.7).

Every 10 s, each local worker announces in Redis which feature lane it serves
and the GPU it sees: engines:local:{feature}:{hostname}, a hash with a 30 s TTL.
The admin view compares these with the configured workers ("configured X, alive
Y") and shows real VRAM use; capacity and routing never depend on them - a
restarting replica must not make the engine look empty.

GPU facts come from `nvidia-smi` (the NVIDIA runtime mounts it into GPU
containers), so no extra Python dependency is needed; without it the worker
reports device "cpu".
"""

import logging
import json
import socket
import subprocess
import threading
import time
from typing import Dict, List, Optional

from celery.signals import worker_ready, worker_shutting_down

from shared.config import get_settings
from shared.engines.features import feature_for_queue
from shared.engines.liveness import KEY, TTL_SECONDS
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 10

_stop = threading.Event()


def detect_gpu() -> Optional[Dict[str, str]]:
    """The first visible GPU's uuid, name and memory (GB), or None without one"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=uuid,name,memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out:
        return None
    uuid, name, total_mib, used_mib = [part.strip() for part in out[0].split(",")]
    return {
        "gpu_uuid": uuid,
        "gpu_name": name,
        "vram_total_gb": f"{float(total_mib) / 1024:.2f}",
        "vram_used_gb": f"{float(used_mib) / 1024:.2f}",
    }


def heartbeat_fields(features: List[str]) -> Dict[str, str]:
    gpu = detect_gpu()
    fields = {"device": "cuda" if gpu else "cpu", "updated_at": f"{time.time():.0f}"}
    if gpu:
        fields.update(gpu)
    if 'document_conversion' in features:
        from shared.document_readiness import worker_readiness
        fields['document_readiness'] = json.dumps(worker_readiness(), separators=(',', ':'))
    return fields


def publish(features: List[str], hostname: str, client=None) -> None:
    client = client or get_redis_client().client
    fields = heartbeat_fields(features)
    pipe = client.pipeline()
    for feature in features:
        key = KEY.format(feature=feature, hostname=hostname)
        pipe.hset(key, mapping=fields)
        pipe.expire(key, TTL_SECONDS)
    pipe.execute()


def _loop(features: List[str], hostname: str) -> None:
    while not _stop.is_set():
        try:
            publish(features, hostname)
        except Exception as e:  # a heartbeat must never take the worker down
            logger.warning(f"[ENGINES] Heartbeat for {features} failed: {e}")
        _stop.wait(INTERVAL_SECONDS)


@worker_ready.connect
def _start(sender=None, **kwargs):
    try:
        queues = [q.name for q in sender.task_consumer.queues]
    except Exception:
        return
    settings = get_settings()
    features = sorted({f for f in (feature_for_queue(q, settings) for q in queues) if f})
    if not features:
        return
    hostname = getattr(sender, "hostname", None) or socket.gethostname()
    threading.Thread(target=_loop, args=(features, hostname), name="engine-heartbeat", daemon=True).start()
    logger.info(f"[ENGINES] Heartbeat started for {features} as {hostname}")


@worker_shutting_down.connect
def _stop_heartbeat(**kwargs):
    _stop.set()
