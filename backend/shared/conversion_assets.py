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
  them (a deletion that fails is postponed ASSET_EXPIRY_RETRY_SECONDS; one
  process at a time, Redis lock `assets:expiry:lock`);
- a job that settles without a manifest (failed, partial) gets one for the
  assets of its completed pages, or its prefix is deleted
  (`settle_unlisted_assets`); a manifest that cannot be written is never
  published (the workers turn the references back into placeholders);
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

# Expired assets deleted per beat run, oldest first; a deletion that failed is
# tried again this much later (so a job MinIO keeps refusing never starves the batch)
ASSET_EXPIRY_BATCH = 20
ASSET_EXPIRY_RETRY_SECONDS = 300


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


_NAME_ORDER = re.compile(r"^p(\d{4})-(?:img(\d+)|page)-")
PUBLIC_FIELDS = ("name", "kind", "page", "bbox", "sha256", "mime", "width", "height", "size_bytes", "url")


def sort_key(asset: dict):
    """Page, then the page render, then the pictures in document order (all read from the name)."""
    match = _NAME_ORDER.match(asset.get("name") or "")
    if match is None:
        return (asset.get("page") or 0, 0 if asset.get("kind") == KIND_PAGE else 1, 0)
    return (int(match.group(1)), 0 if match.group(2) is None else 1, int(match.group(2) or 0))


def public_asset(asset: dict) -> dict:
    """Only the published fields of an asset, whatever a stored copy carries."""
    return {field: asset.get(field) for field in PUBLIC_FIELDS}


def public_assets(assets) -> list:
    return [public_asset(a) for a in sorted(assets or [], key=sort_key) if isinstance(a, dict)]


def slot_of(kind: str, page: Optional[int], index: int = 0) -> str:
    """A position in the document, independent of the bytes (a retry of the same page reuses it)."""
    return f"p{(page or 0):04d}-page" if kind == KIND_PAGE else f"p{(page or 0):04d}-img{index:02d}"


# ---------------------------------------------------------------------------
# Per-MAIN-job budget (split PDFs)
# ---------------------------------------------------------------------------

BUDGET_TTL_SECONDS = 24 * 3600


class JobAssetBudget:
    """
    The per-job limits (CONVERSION_ASSET_MAX_COUNT / _MAX_TOTAL_MB) shared by the
    page jobs of one split PDF, reserved in Redis BEFORE a page job encodes and
    uploads an asset, so a 500-page `page_images` job stops storing at the cap
    instead of uploading everything and trimming at the merge.

    Keys: `job:{id}:assets:slots` (hash: slot -> bytes) and `job:{id}:assets:bytes`.
    A slot is a position (`p0003-img02`, `p0003-page`), so a page retry reuses
    its reservation instead of counting twice. `precheck` refuses a new slot once
    the count or the bytes are used up (before encoding); `commit` reserves the
    encoded size and gives it back when that goes over (before uploading).
    Concurrent pages may both overshoot and both give back: conservative, never
    over the cap.

    Redis is only the fast path: any Redis error answers None ("unknown") and the
    page job falls back to its own per-page limits; the merge (`combine_pages`,
    in page order) stays the authority over what the manifest lists. Which pages
    get the budget depends on the order the pages finish in.
    """

    def __init__(self, redis_client, job_id: str, *, max_count: int, max_bytes: int):
        self.redis = getattr(redis_client, "client", redis_client)
        self.slots_key = f"job:{job_id}:assets:slots"
        self.bytes_key = f"job:{job_id}:assets:bytes"
        self.max_count = max_count
        self.max_bytes = max_bytes

    def precheck(self, slot: str) -> tuple:
        """(True | False | None, reason): may this slot still be stored?"""
        try:
            if self.redis.hexists(self.slots_key, slot):
                return True, None
            if int(self.redis.hlen(self.slots_key) or 0) >= self.max_count:
                return False, "count_limit"
            if int(self.redis.get(self.bytes_key) or 0) >= self.max_bytes:
                return False, "size_limit"
            return True, None
        except Exception as e:  # noqa: BLE001 - per-page limits + the merge decide
            logger.warning(f"[ASSETS] Budget unavailable ({e}); per-page limits apply")
            return None, None

    def commit(self, slot: str, size: int) -> tuple:
        """(True | False | None, reason): reserve `size` bytes for `slot`."""
        try:
            if not self.redis.hsetnx(self.slots_key, slot, size):
                previous = int(self.redis.hget(self.slots_key, slot) or 0)
                if previous != size:  # a retry re-encoded the same position
                    self.redis.hset(self.slots_key, slot, size)
                    self.redis.incrby(self.bytes_key, size - previous)
                return True, None
            total = int(self.redis.incrby(self.bytes_key, size))
            count = int(self.redis.hlen(self.slots_key))
            self.redis.expire(self.slots_key, BUDGET_TTL_SECONDS)
            self.redis.expire(self.bytes_key, BUDGET_TTL_SECONDS)
            if count > self.max_count or total > self.max_bytes:
                self.redis.hdel(self.slots_key, slot)
                self.redis.decrby(self.bytes_key, size)
                return False, "count_limit" if count > self.max_count else "size_limit"
            return True, None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[ASSETS] Budget unavailable ({e}); per-page limits apply")
            return None, None


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
        for asset in public_assets(assets):
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


def page_results(job_id: str, redis_client) -> list:
    """[(page_number, markdown, assets, skipped)] of the completed page jobs of a split PDF (Redis)."""
    out = []
    for page_job_id in redis_client.get_page_jobs(job_id) or []:
        status = redis_client.get_job_status(page_job_id) or {}
        result = redis_client.get_job_result(page_job_id) if status.get("status") == "completed" else None
        if result:
            out.append((status.get("page_number"), result.get("markdown") or "", result.get("assets") or [],
                        result.get("assets_skipped")))
    return out


def settle_unlisted_assets(job: Job, minio_factory: Callable, redis_factory: Optional[Callable] = None) -> bool:
    """
    A job that settled (completed, failed or partial) without a manifest although
    it asked for assets: nothing could download what its pages stored.

    - Pages that completed and still have their result (a PARTIAL split PDF, or a
      FAILED one whose merge failed) get a manifest of their assets, so the URLs in
      those page results work and follow the normal retention (purge_source /
      DELETE /jobs/{id}/source / DELETE /jobs/{id});
    - nothing listable (a failed single document, page results expired, Redis
      down): the `assets/{id}/` prefix is deleted.

    The caller holds the job's row lock and commits. Returns True when the job row
    changed. Never raises.
    """
    from shared.config import get_settings
    from shared.models import JobStatus

    if manifest_of(job) is not None or not wants_assets(job_options(job)):
        return False
    if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PARTIAL, JobStatus.CANCELLED):
        return False
    settings = get_settings()
    assets, skipped, dropped = [], empty_skipped(), []
    try:
        if redis_factory is None:
            from shared.redis_client import get_redis_client as redis_factory
        pages = page_results(job.id, redis_factory())
        _, assets, skipped, dropped = combine_pages(
            job.id, pages, max_count=int(settings.conversion_asset_max_count),
            max_bytes=int(settings.conversion_asset_max_total_mb) * 1024 * 1024)
    except Exception as e:  # noqa: BLE001 - nothing listable: delete below
        logger.warning(f"[JOB {job.id}] Could not list the page assets: {e}")
        assets = []
    try:
        minio = minio_factory()
        if not assets:
            minio.delete_folder(minio.bucket_results, asset_prefix(job.id))
            return False
        for asset in dropped:
            minio.delete_file(minio.bucket_results, object_name(job.id, asset["name"]))
    except Exception as e:  # noqa: BLE001 - DELETE /jobs/{id} removes them later
        logger.warning(f"[JOB {job.id}] Could not delete unlisted assets: {e}")
        if not assets:
            return False
    job.assets_manifest = {"assets": assets, "skipped": skipped}
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
        except Exception as e:  # noqa: BLE001 - retried later, behind the other jobs
            logger.warning(f"[JOB {job_id}] Could not delete the expired image assets: {e}")
            _postpone_expiry(session_factory, job_id, now)
    return done


def _postpone_expiry(session_factory, job_id: str, now: datetime) -> None:
    from shared.job_source import lock_job

    try:
        with session_factory() as db:
            job = lock_job(db, job_id)
            if job is not None and job.assets_deleted_at is None and job.assets_expire_at is not None:
                job.assets_expire_at = now + timedelta(seconds=ASSET_EXPIRY_RETRY_SECONDS)
            db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[JOB {job_id}] Could not postpone the asset expiry: {e}")
