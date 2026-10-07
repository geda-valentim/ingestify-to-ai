"""
Which files a Modal deploy ships into the image, and the requirements it installs.

Standard library only: imported by the deploy (image.py), by the fingerprint
(API, dispatcher) and by the container itself.
"""

from pathlib import Path
from typing import List

# Environment of the deploy subprocess (and, baked into the image, of the container)
DEPLOY_ENV = "INGESTIFY_MODAL_DEPLOY"
ALLOW_UNHASHED_ENV = "INGESTIFY_MODAL_ALLOW_UNHASHED"

MODAL_APPS_DIR = Path(__file__).resolve().parent
WORKERS_DIR = MODAL_APPS_DIR.parent.parent
BACKEND_DIR = WORKERS_DIR.parent
REQUIREMENTS_IN = MODAL_APPS_DIR / "requirements-whisper-modal.in"
LOCK_FILE = MODAL_APPS_DIR / "requirements-whisper-modal.lock"

# Shipped into the image under /root/<path relative to the backend>, in this order
SOURCE_FILES: List[Path] = [
    BACKEND_DIR / "shared" / "__init__.py",
    BACKEND_DIR / "shared" / "audio_decoding.py",
    WORKERS_DIR / "__init__.py",
    WORKERS_DIR / "audio" / "__init__.py",
    WORKERS_DIR / "audio" / "feature_extractor.py",
    WORKERS_DIR / "audio" / "decoding_options.py",
    WORKERS_DIR / "audio" / "analysis.py",
    WORKERS_DIR / "engines" / "__init__.py",
    WORKERS_DIR / "engines" / "whisper_core.py",
    MODAL_APPS_DIR / "__init__.py",
    MODAL_APPS_DIR / "files.py",
    MODAL_APPS_DIR / "protocol.py",
    MODAL_APPS_DIR / "runner.py",
    MODAL_APPS_DIR / "image.py",
    MODAL_APPS_DIR / "whisper_app.py",
]


def lock_is_hashed(path: Path = LOCK_FILE) -> bool:
    """True when the lock exists and every requirement in it carries a --hash"""
    if not path.exists():
        return False
    requirements, hashed, pending = 0, 0, ""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pending += " " + line.rstrip("\\")
        if line.endswith("\\"):
            continue
        if not pending.strip().startswith("--"):
            requirements += 1
            hashed += "--hash=sha256:" in pending
        pending = ""
    return requirements > 0 and requirements == hashed
