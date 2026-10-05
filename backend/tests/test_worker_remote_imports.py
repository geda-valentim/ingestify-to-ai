"""
worker-remote runs a slim image (docker/Dockerfile.remote, requirements-remote.txt):
no docling, torch, faster-whisper or PyAV. Its Celery app and every module it
runs must import without them - checked here by blocking those packages in a
fresh interpreter (spec 0003, slice 4a).
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

SCRIPT = r"""
import importlib.abc, sys
BLOCKED = ("docling", "torch", "torchvision", "transformers", "faster_whisper", "ctranslate2", "av",
           "playwright", "modal", "PyPDF2", "pypdf")

class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"blocked in worker-remote: {name}")
        return None

sys.meta_path.insert(0, Block())
import workers.celery_app
import workers.engines.remote_tasks
import workers.engines.remote
import workers.engines.modal_deploy
import workers.engines.pipeline
import workers.engines.adapters.modal
import workers.engines.modal_apps.fingerprint
print("ok")
"""


def test_worker_remote_modules_import_without_heavy_packages():
    done = subprocess.run([sys.executable, "-c", SCRIPT], cwd=BACKEND, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().endswith("ok")
