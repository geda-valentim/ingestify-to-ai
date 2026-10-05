"""
The container image of the Modal Whisper app (spec 0003, Appendix F).

    debian_slim, Python 3.13 (the local worker's version, for parity)
    + requirements-whisper-modal.lock: every pin with its sha256, installed with
      pip --require-hashes --no-deps (an unhashed install needs --allow-unhashed)
    + Whisper weights downloaded at build time at a pinned Hugging Face revision
      (MODEL_REVISION), so a container never downloads anything at start
    + the deploy spec (binding, fingerprint) as an environment variable, so the
      container's import of whisper_app.py rebuilds the same decorator
    + the few source files the container runs (files.SOURCE_FILES), last,
      so a code change does not rebuild the dependency and weight layers

What is NOT pinned by hash: the debian_slim base image itself (Modal builds it;
pinned by Modal's image builder version, not by digest), the apt packages Modal
installs into it, and pip/uv as Modal ships them. The weights are pinned by
revision (a git commit of the model repository), which Hugging Face serves
immutably.

Imports `modal`: only the deploy (worker-remote's CLI) and the container load it.
"""

import json
from typing import Dict

import modal

from workers.engines.modal_apps import protocol
from workers.engines.modal_apps.files import (  # noqa: F401  (DEPLOY_ENV re-exported)
    BACKEND_DIR, DEPLOY_ENV, LOCK_FILE, REQUIREMENTS_IN, SOURCE_FILES, lock_is_hashed,
)

PYTHON_VERSION = "3.13"
_SITE = f"/usr/local/lib/python{PYTHON_VERSION}/site-packages/nvidia"
CUDA_LIBRARY_PATH = f"{_SITE}/cublas/lib:{_SITE}/cudnn/lib"

REMOTE_ROOT = "/root"


def _weights_command() -> str:
    return (
        "python -c \"from huggingface_hub import snapshot_download; "
        f"snapshot_download('{protocol.MODEL_REPO}', revision='{protocol.MODEL_REVISION}', "
        f"local_dir='{protocol.MODEL_DIR}')\""
    )


def build_image(spec: Dict[str, object], *, allow_unhashed: bool = False) -> "modal.Image":
    image = modal.Image.debian_slim(python_version=PYTHON_VERSION)
    if lock_is_hashed():
        image = image.pip_install_from_requirements(str(LOCK_FILE), extra_options="--require-hashes --no-deps")
    elif allow_unhashed:
        image = image.pip_install_from_requirements(str(REQUIREMENTS_IN))
    else:
        raise RuntimeError(f"{LOCK_FILE.name} is missing or not fully hashed: run `scripts/engines.py modal-lock` "
                           "first (or deploy with --allow-unhashed, recorded on the engine)")
    image = (
        image.run_commands(_weights_command())
        .env({
            "LD_LIBRARY_PATH": CUDA_LIBRARY_PATH,
            "HF_HUB_OFFLINE": "1",
            "PYTHONPATH": REMOTE_ROOT,
            DEPLOY_ENV: json.dumps(spec, sort_keys=True),
        })
    )
    for path in SOURCE_FILES + [REQUIREMENTS_IN] + ([LOCK_FILE] if LOCK_FILE.exists() else []):
        image = image.add_local_file(path, f"{REMOTE_ROOT}/{path.relative_to(BACKEND_DIR).as_posix()}")
    return image
