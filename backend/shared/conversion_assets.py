"""
Image assets of a document conversion (`image_mode`, `page_images` on /upload and
/convert).

- `image_mode=referenced`: every picture docling finds (PictureItem) is stored as
  a PNG and the markdown references it (`![...](/jobs/{job_id}/assets/{name})`)
  where the export used to write the `<!-- image -->` placeholder;
- `page_images=true`: every PDF page is rendered to a PNG (kind "page"), not
  referenced from the markdown.

Where they live: the results bucket, `assets/{main_job_id}/{name}`, always under
the MAIN job id (a split PDF's page jobs write there directly, with the absolute
page number). The durable list is `Job.assets_manifest`
(`{"assets": [...], "skipped": {...}}`), written with the job's completion; the
result (`GET /jobs/{id}/result`) carries the same list as `assets`, ordered by
page, then the page render, then the pictures in document order.

Names: `p{page:04d}-img{idx:02d}-{sha256[:12]}.png` for a picture (idx is its
1-based position on the page) and `p{page:04d}-page-{sha256[:12]}.png` for a page
render (page 0000 when the format has no pages). `GET /jobs/{id}/assets/{name}`
only serves a name listed in the job's manifest (`find_asset`), never a path.

Lifetime (they are *outputs* the client must download, not source files):

- they are NOT deleted when the job settles, even with `purge_source=true`; the
  purge then schedules their deletion `ASSET_RETENTION_SECONDS` later
  (`Job.assets_expire_at`, `schedule_expiry`) and the periodic beat
  (`expire_due_assets`, bounded and idempotent, under the job's row lock) deletes
  them;
- `DELETE /jobs/{id}/source` deletes them right away, `DELETE /jobs/{id}` too;
- without purge_source they live as long as the job.

Once deleted `Job.assets_deleted_at` is set and the asset route answers 410
SOURCE_PURGED (cause ASSETS_PURGED); the manifest is kept, so a known name is
told apart from an unknown one (404).
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Callable, Optional

from shared.models import Job

logger = logging.getLogger(__name__)

IMAGE_MODE_OPTION = "image_mode"
PAGE_IMAGES_OPTION = "page_images"
IMAGE_MODE_NONE = "none"
IMAGE_MODE_REFERENCED = "referenced"
IMAGE_MODES = (IMAGE_MODE_NONE, IMAGE_MODE_REFERENCED)

KIND_PICTURE = "picture"
KIND_PAGE = "page"
ASSET_MIME = "image/png"

ASSET_AREA = "assets"
# Exactly what the workers write; anything else is not an asset name
ASSET_NAME = re.compile(r"^p\d{4}-(?:img\d{2,}|page)-[0-9a-f]{12}\.png$")
SKIP_REASONS = ("too_small", "count_limit", "size_limit", "unavailable")

# Expired assets deleted per beat run, oldest first
ASSET_EXPIRY_BATCH = 20


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

def normalize_options(image_mode: Optional[str], page_images) -> tuple:
    """(image_mode, page_images) with the defaults applied."""
    mode = (image_mode or IMAGE_MODE_NONE).strip().lower()
    return mode, page_images is True


def requested_options(image_mode: str, page_images: bool) -> dict:
    """The non-default options, as stored in the job's requested configuration."""
    options = {}
    if image_mode != IMAGE_MODE_NONE:
        options[IMAGE_MODE_OPTION] = image_mode
    if page_images:
        options[PAGE_IMAGES_OPTION] = True
    return options


def save_options(db, job: Job, image_mode: str, page_images: bool) -> None:
    """Durable with the job (JobConfiguration.options); nothing stored for the defaults. No commit."""
    from shared.job_source import _set_requested_option

    for key, value in requested_options(image_mode, page_images).items():
        _set_requested_option(db, job, key, value)


def job_options(job: Optional[Job]) -> dict:
    """{"image_mode": ..., "page_images": ...} of a job, from its requested configuration."""
    row = getattr(job, "configuration_row", None) if job is not None else None
    options = getattr(row, "options", None) if row is not None else None
    options = options if isinstance(options, dict) else {}
    mode = options.get(IMAGE_MODE_OPTION) or IMAGE_MODE_NONE
    return {IMAGE_MODE_OPTION: mode if mode in IMAGE_MODES else IMAGE_MODE_NONE,
            PAGE_IMAGES_OPTION: options.get(PAGE_IMAGES_OPTION) is True}


def durable_options(job_id: str, session_factory) -> dict:
    """The image options of a MAIN job, read from the DB (retries and merges honour them)."""
    try:
        with session_factory() as db:
            return job_options(db.get(Job, job_id))
    except Exception as e:  # noqa: BLE001 - the Celery message still carries them
        logger.warning(f"[JOB {job_id}] Could not read the image options: {e}")
        return {}


def wants_assets(options: Optional[dict]) -> bool:
    options = options or {}
    return options.get(IMAGE_MODE_OPTION) == IMAGE_MODE_REFERENCED or options.get(PAGE_IMAGES_OPTION) is True


# ---------------------------------------------------------------------------
# Names, keys, URLs
# ---------------------------------------------------------------------------

def picture_name(page: Optional[int], index: int, sha256: str) -> str:
    return f"p{(page or 0):04d}-img{index:02d}-{sha256[:12]}.png"


def page_name(page: int, sha256: str) -> str:
    return f"p{page:04d}-page-{sha256[:12]}.png"


def asset_prefix(job_id: str) -> str:
    return f"{ASSET_AREA}/{job_id}/"


def object_name(job_id: str, name: str) -> str:
    return f"{asset_prefix(job_id)}{name}"


def asset_url(job_id: str, name: str) -> str:
    return f"/jobs/{job_id}/assets/{name}"


def sort_key(asset: dict):
    """Page, then the page render, then the pictures in document order."""
    return (asset.get("page") or 0, 0 if asset.get("kind") == KIND_PAGE else 1, asset.get("position", 0))


def public_asset(asset: dict) -> dict:
    """The manifest entry without worker bookkeeping (position)."""
    return {k: v for k, v in asset.items() if k != "position"}


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def empty_skipped() -> dict:
    return {reason: 0 for reason in SKIP_REASONS}


def merge_skipped(*counts) -> dict:
    total = empty_skipped()
    for count in counts:
        for reason, value in (count or {}).items():
            total[reason] = total.get(reason, 0) + int(value or 0)
    return total


def manifest_of(job: Optional[Job]) -> Optional[dict]:
    manifest = getattr(job, "assets_manifest", None) if job is not None else None
    return manifest if isinstance(manifest, dict) else None


def assets_of(job: Optional[Job]) -> list:
    manifest = manifest_of(job)
    assets = manifest.get("assets") if manifest else None
    return assets if isinstance(assets, list) else []


def assets_available(job: Optional[Job]) -> bool:
    """The job has assets and they were not deleted (purge, DELETE /jobs/{id}/source)."""
    return bool(assets_of(job)) and getattr(job, "assets_deleted_at", None) is None


def assets_expire_at(job: Optional[Job]) -> Optional[datetime]:
    """When the beat deletes them (UTC), or None (kept as long as the job)."""
    if not assets_available(job):
        return None
    return getattr(job, "assets_expire_at", None)


def find_asset(job: Optional[Job], name: str) -> Optional[dict]:
    """The manifest entry for `name`, or None. Only listed names are ever served."""
    if not isinstance(name, str) or not ASSET_NAME.match(name):
        return None
    return next((asset for asset in assets_of(job) if asset.get("name") == name), None)


def result_fields(job: Optional[Job]) -> dict:
    """`assets` / `assets_skipped` of GET /jobs/{id}/result, from the durable manifest."""
    manifest = manifest_of(job)
    if manifest is None:
        return {}
    return {"assets": [public_asset(a) for a in assets_of(job)],
            "assets_skipped": merge_skipped(manifest.get("skipped"))}


_REFERENCE = r"!\[[^\]]*\]\({url}\)"


def unreference(markdown: str, url: str, placeholder: str = "<!-- image -->") -> str:
    """Turn the markdown reference to `url` back into docling's image placeholder."""
    return re.sub(_REFERENCE.format(url=re.escape(url)), placeholder, markdown or "")


def combine_pages(job_id: str, pages, *, max_count: int, max_bytes: int):
    """
    The merge of a split PDF: `pages` = [(page_number, markdown, assets, skipped)].

    Returns (markdowns in page order, assets, skipped, dropped): the assets concatenated in
    page order with their URLs under the MAIN job, and the per-job limits applied
    across pages (a page job only knows its own page): an asset past the limits is
    dropped from the list, its markdown reference is turned back into the
    placeholder, and it is returned in `dropped` for the caller to delete.
    """
    pages = sorted(pages, key=lambda p: p[0])
    out_markdown, out_assets, dropped = [], [], []
    skipped = empty_skipped()
    count = total = 0
    for _page, markdown, assets, page_skipped in pages:
        skipped = merge_skipped(skipped, page_skipped)
        for asset in sorted(assets or [], key=sort_key):
            asset = dict(asset)
            url = asset_url(job_id, asset["name"])
            if asset.get("url") and asset["url"] != url:
                markdown = (markdown or "").replace(f"({asset['url']})", f"({url})")
            asset["url"] = url
            size = int(asset.get("size_bytes") or 0)
            if count + 1 > max_count or total + size > max_bytes:
                skipped["count_limit" if count + 1 > max_count else "size_limit"] += 1
                markdown = unreference(markdown, url)
                dropped.append(asset)
                continue
            count += 1
            total += size
            out_assets.append(asset)
        out_markdown.append(markdown)
    return out_markdown, out_assets, skipped, dropped


# ---------------------------------------------------------------------------
# Deleting them
# ---------------------------------------------------------------------------

class AssetDeleteError(RuntimeError):
    """The assets exist but could not be deleted (MinIO refused or is down)."""


def delete_assets(db, job: Job, minio_factory: Callable, *, commit: bool = True) -> bool:
    """
    Delete a job's stored assets (`assets/{job_id}/` in the results bucket) and
    record `assets_deleted_at`. The manifest is kept (410 for a known name).

    The caller holds the job's row lock. Returns False when there was nothing to
    delete. Raises AssetDeleteError when MinIO refused (nothing recorded).
    """
    if not assets_available(job):
        return False
    minio = minio_factory()
    try:
        deleted = minio.delete_folder(minio.bucket_results, asset_prefix(job.id))
    except Exception as e:  # noqa: BLE001 - one error for the caller
        raise AssetDeleteError(str(e)) from e
    if not deleted:
        raise AssetDeleteError(f"MinIO did not delete {asset_prefix(job.id)}")
    job.assets_deleted_at = datetime.utcnow()
    job.assets_expire_at = None
    if commit:
        db.commit()
    return True


def schedule_expiry(job: Optional[Job], now: Optional[datetime] = None) -> bool:
    """
    purge_source on a settled job: its assets go `ASSET_RETENTION_SECONDS` from now
    (never at once: the client still has to download them). Idempotent: an expiry
    already scheduled is kept. No commit.
    """
    from shared.config import get_settings

    if not assets_available(job) or getattr(job, "assets_expire_at", None) is not None:
        return False
    retention = max(0, int(get_settings().asset_retention_seconds))
    job.assets_expire_at = (now or datetime.utcnow()) + timedelta(seconds=retention)
    return True


def expire_due_assets(session_factory, minio_factory: Callable, *, now: Optional[datetime] = None,
                      limit: int = ASSET_EXPIRY_BATCH) -> int:
    """
    The periodic beat: delete the assets whose `assets_expire_at` passed. Bounded
    (`limit` jobs per call, oldest expiry first) and idempotent: each job is
    re-read under its row lock and re-checked, and a deletion sets
    `assets_deleted_at`, which takes the job out of the query. A deletion that
    fails is logged and retried on the next run. Returns how many were deleted.
    Never raises.
    """
    from shared.job_source import lock_job

    now = now or datetime.utcnow()
    try:
        with session_factory() as db:
            job_ids = [row[0] for row in db.query(Job.id).filter(
                Job.assets_expire_at.isnot(None),
                Job.assets_expire_at <= now,
                Job.assets_deleted_at.is_(None),
            ).order_by(Job.assets_expire_at).limit(limit)]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ASSETS] Could not list expired assets: {e}")
        return 0
    done = 0
    for job_id in job_ids:
        try:
            with session_factory() as db:
                job = lock_job(db, job_id)
                expire_at = getattr(job, "assets_expire_at", None)
                if job is None or expire_at is None or expire_at > now or not assets_available(job):
                    db.rollback()
                    continue
                if delete_assets(db, job, minio_factory):
                    done += 1
                    logger.info(f"[JOB {job_id}] Image assets deleted (retention over, purge_source)")
        except Exception as e:  # noqa: BLE001 - next run tries again
            logger.warning(f"[JOB {job_id}] Could not delete the expired image assets: {e}")
    return done
