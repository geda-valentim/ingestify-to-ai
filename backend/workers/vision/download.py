"""
Prefetch the Florence-2 weights into the shared cache.

Run it as ``python -m workers.vision.download`` (or ``make vision-download``).
Air-gapped and CI deployments set ``VISION_ALLOW_MODEL_DOWNLOAD=false`` and use
this to populate the cache ahead of time; everyone else uses it to avoid paying
a ~0.5GB download inside the first request's 60s budget, which would otherwise
504 on a cold container.

This module lives inside ``backend/workers/vision/`` rather than under
``scripts/`` deliberately: ``.dockerignore`` excludes ``scripts/`` wholesale and
only re-includes named files, so a downloader placed there would silently never
reach the image.
"""

import argparse
import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)


def model_is_cached(model_id: str, revision: str, cache_dir: str) -> bool:
    """Is this exact model+revision already in the local cache?

    Never touches the network: ``local_files_only=True`` makes the call resolve
    against the cache alone. Used by the capabilities probe, so it must be both
    cheap and incapable of blocking.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return False

    try:
        snapshot_download(
            repo_id=model_id,
            revision=revision,
            cache_dir=cache_dir,
            local_files_only=True,
        )
        return True
    except Exception:
        return False


def download_model(
    model_id: Optional[str] = None,
    revision: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> str:
    """Download the pinned model into the cache and return the snapshot path.

    The revision is always a commit sha, never a branch: a floating branch would
    make every deployment a fresh, unreviewed set of weights.
    """
    from shared.config import get_settings

    settings = get_settings()
    model_id = model_id or settings.vision_model_id
    revision = revision or settings.vision_model_revision
    cache_dir = cache_dir or settings.vision_model_cache_dir

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is not installed. Install the vision extra first: "
            "pip install -r backend/requirements-vision.txt"
        ) from exc

    logger.info("Downloading %s@%s into %s ...", model_id, revision, cache_dir)
    path = snapshot_download(
        repo_id=model_id,
        revision=revision,
        cache_dir=cache_dir,
    )
    logger.info("Done: %s", path)
    return path


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m workers.vision.download",
        description="Prefetch the Florence-2 weights into the shared model cache.",
    )
    parser.add_argument("--model-id", default=None, help="Override VISION_MODEL_ID")
    parser.add_argument("--revision", default=None, help="Override VISION_MODEL_REVISION (commit sha)")
    parser.add_argument("--cache-dir", default=None, help="Override VISION_MODEL_CACHE_DIR")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        path = download_model(args.model_id, args.revision, args.cache_dir)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Download failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
