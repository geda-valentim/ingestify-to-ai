"""
The describe stage of a document conversion (`describe_images` / `ocr_images`;
shared/figure_descriptions.py has the pure parts).

    conversion (single document) / merge (split PDF)
        -> begin(): pending.json in MinIO, one vision task per unique figure
           (engine routing: dispatch.place_now on the `vision` feature, exactly
           as the image routes place theirs), a stall watchdog; returns at once
    describe_figure_task (vision queue, one per unique image): caption and/or
           OCR, outcome recorded in Redis; the last one queues the finalize
    finalize_figures_task (default queue): rewrites the markdown, completes the
           MAIN job, deletes the temporary figures, then purge_source

No conversion worker ever waits on the vision worker: the stage is driven by
messages, so a full general pool cannot deadlock against a busy vision queue.
The MAIN job stays PROCESSING (progress 90 -> 99) until the text is inlined, so
`has_pending_work` keeps purge_source away from the images the vision worker reads.

A figure whose vision task fails (model missing, timeout, no engine) gets no
text and is counted in `figures_skipped`; it never fails the job. A vision
worker killed mid-task never reports: the watchdog finalizes with what it has
once no figure settled for CONVERSION_FIGURE_STALL_SECONDS.
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

from celery.exceptions import SoftTimeLimitExceeded

from shared import conversion_assets
from shared import figure_descriptions as fd
from shared.config import get_settings
from shared.database import SessionLocal
from shared.models import Job, JobStatus
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

DESCRIBE_TASK = "workers.vision_tasks.describe_figure_task"
FINALIZE_TASK = "workers.tasks.finalize_figures_task"
STAGE_PROGRESS_START = 90
STAGE_PROGRESS_SPAN = 9
FINALIZE_LOCK_SECONDS = 600


def _redis():
    from shared.redis_client import get_redis_client

    return get_redis_client()


def _minio():
    from shared.minio_client import get_minio_client

    return get_minio_client()


def _es():
    from shared.elasticsearch_client import get_es_client

    return get_es_client()


# ---------------------------------------------------------------------------
# Starting the stage
# ---------------------------------------------------------------------------

def figure_options(job_id: str) -> dict:
    """describe_images / ocr_images of the MAIN job, from the DB (durable)."""
    options = conversion_assets.durable_options(job_id, SessionLocal)
    return {"describe": options.get(conversion_assets.DESCRIBE_IMAGES_OPTION) is True,
            "ocr": options.get(conversion_assets.OCR_IMAGES_OPTION) is True,
            "image_mode": options.get(conversion_assets.IMAGE_MODE_OPTION) or conversion_assets.IMAGE_MODE_NONE}


def wanted(job_id: str, options: Optional[dict] = None) -> bool:
    """The job asked for descriptions / OCR (the run's options, else the durable ones)."""
    if conversion_assets.wants_figures(options):
        return True
    found = figure_options(job_id)
    return found["describe"] or found["ocr"]


def begin(job_id: str, result: dict, *, total_pages: Optional[int] = None, callback_url: Optional[str] = None,
          has_manifest: bool = False, dispatch: Optional[Callable] = None) -> dict:
    """
    Start the describe stage of a converted document (`result`: markdown with the
    figure anchors, metadata, assets, and `figures`, the entries). Returns at once.
    """
    entries = list(result.pop("figures", None) or [])
    options = figure_options(job_id)
    work = fd.plan(entries, int(settings.conversion_figure_max_count))
    pending = {
        "result": result, "entries": entries, "work": work, "total_pages": total_pages,
        "callback_url": callback_url, "has_manifest": has_manifest,
        "describe": options["describe"], "ocr": options["ocr"],
        "caption_task": fd.caption_task(settings.conversion_figure_caption_task),
    }
    logger.info(f"[MAIN JOB {job_id}] Describe stage: {len(entries)} figures, {len(work)} unique to send "
                f"(describe={options['describe']}, ocr={options['ocr']})")
    if not work or not (options["describe"] or options["ocr"]):
        return finalize(job_id, pending, {})

    storage = _minio()
    storage.upload_file(bucket_name=storage.bucket_results, object_name=fd.pending_object(job_id),
                        file_data=fd.dumps(pending).encode("utf-8"), content_type="application/json")
    redis_client = _redis()
    client = redis_client.client
    client.delete(fd.results_key(job_id), fd.finalizing_key(job_id))
    client.set(fd.total_key(job_id), len(work), ex=fd.RESULTS_TTL_SECONDS)
    redis_client.update_job_progress(job_id, STAGE_PROGRESS_START, stage="describing_figures",
                                     figures_done=0, figures_total=len(work))

    user_id = _user_of(job_id)
    for item in work:
        kwargs = {"job_id": job_id, "sha256": item["sha256"], "object_name": item["object"],
                  "describe": pending["describe"], "ocr": pending["ocr"], "caption_task": pending["caption_task"]}
        try:
            sent = (dispatch or _dispatch)(job_id, user_id, kwargs)
        except Exception as e:  # noqa: BLE001 - that figure is skipped, the others go on
            logger.warning(f"[MAIN JOB {job_id}] Could not queue figure {item['sha256'][:12]}: {e}")
            sent = False
        if not sent:
            record(job_id, item["sha256"], {"description": None, "ocr_text": None, "error": "VISION_UNAVAILABLE"})
    finalize_figures_task.apply_async(kwargs={"job_id": job_id, "watchdog": True, "seen": 0},
                                      countdown=int(settings.conversion_figure_stall_seconds))
    return {"job_id": job_id, "status": "describing_figures", "figures": len(work)}


def _user_of(job_id: str) -> Optional[str]:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            return job.user_id if job else None
    except Exception:  # noqa: BLE001
        return None


def _dispatch(job_id: str, user_id: Optional[str], kwargs: dict) -> bool:
    """
    One figure to the vision worker, through the vision route when there is one
    (spec 0003: a free engine slot becomes a reservation the task claims; no route
    or no slot with a local step -> the vision queue as today). False: no engine
    can take it (the figure is skipped).
    """
    from shared.engines import dispatch as engine_dispatch

    try:
        from shared.iam.remote import remote_use_of

        placement = engine_dispatch.place_now(
            feature="vision", subject_id=f"{job_id}:{kwargs['sha256'][:16]}", job_id=job_id, user_id=user_id,
            remote_use=remote_use_of(user_id, session_factory=SessionLocal), session_factory=SessionLocal)
    except Exception as e:  # noqa: BLE001 - routing never fails what would run without it
        logger.warning(f"[MAIN JOB {job_id}] Vision placement failed, using the vision queue: {e}")
        placement = engine_dispatch.Placement("today")
    if placement.outcome == "unavailable":
        logger.warning(f"[MAIN JOB {job_id}] No vision engine for a figure: {placement.reason}")
        return False
    if placement.outcome == "placed":
        kwargs = {**kwargs, "usage_id": placement.usage_id}
        engine_dispatch.publish_sync(SessionLocal, placement.usage_id,
                                     lambda: describe_figure_task.apply_async(kwargs=kwargs))
        return True
    describe_figure_task.apply_async(kwargs=kwargs)
    return True


# ---------------------------------------------------------------------------
# The vision side
# ---------------------------------------------------------------------------

def record(job_id: str, sha256: str, outcome: dict, *, queue_finalize: bool = True) -> int:
    """Store one image's outcome; the one that completes the set queues the finalize. Never raises."""
    try:
        redis_client = _redis()
        client = redis_client.client
        client.hset(fd.results_key(job_id), sha256, fd.dumps(outcome))
        client.expire(fd.results_key(job_id), fd.RESULTS_TTL_SECONDS)
        done = int(client.hlen(fd.results_key(job_id)) or 0)
        total = int(client.get(fd.total_key(job_id)) or 0)
        if total:
            share = min(done, total) / total
            redis_client.update_job_progress(job_id, STAGE_PROGRESS_START + int(share * STAGE_PROGRESS_SPAN),
                                             stage="describing_figures", figures_done=min(done, total),
                                             figures_total=total)
        if queue_finalize and total and done >= total:
            celery_app.send_task(FINALIZE_TASK, kwargs={"job_id": job_id})
        return done
    except Exception as e:  # noqa: BLE001 - the watchdog finalizes anyway
        logger.warning(f"[MAIN JOB {job_id}] Could not record figure {sha256[:12]}: {e}")
        return 0


def describe_one(image_path: Path, *, describe: bool, ocr: bool, caption_task: str, describer=None) -> dict:
    """Caption and/or OCR of one image file. Each operation fails on its own (error code kept)."""
    from workers.vision.errors import VisionError
    from workers.vision.factory import get_image_describer

    outcome = {"description": None, "ocr_text": None}
    errors = {}
    describer = describer or get_image_describer()
    if describe:
        try:
            outcome["description"] = str(describer.describe(image_path, {"task": caption_task}).get("description") or "")
        except VisionError as e:
            errors["description"] = e.error_code
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:  # noqa: BLE001 - one figure, never the job
            logger.warning(f"vision figure caption failed: {type(e).__name__}: {e}")
            errors["description"] = "VISION_INFERENCE_FAILED"
    if ocr:
        try:
            outcome["ocr_text"] = str(describer.analyze(image_path, {"task": fd.OCR_TASK}).get("text") or "")
        except VisionError as e:
            errors["ocr"] = e.error_code
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"vision figure OCR failed: {type(e).__name__}: {e}")
            errors["ocr"] = "VISION_INFERENCE_FAILED"
    if errors:
        outcome["errors"] = errors
    return outcome


def _accounted(usage_id: Optional[int], work: Callable[[], dict]) -> dict:
    """Run `work` under a vision-route reservation (claim, heartbeat, settle), like the image routes."""
    if usage_id is None:
        return work()
    from shared.engines import ledger
    from workers.engines.local import UsageHeartbeat

    holder = ledger.holder_id()
    try:
        outcome, _ = ledger.claim(usage_id, holder)
    except Exception as e:  # noqa: BLE001 - accounting never costs the figure
        logger.warning(f"vision figure: could not claim usage {usage_id}: {e}")
        outcome = ledger.LOST
    if outcome != ledger.CLAIMED:
        return work()
    heartbeat = UsageHeartbeat(usage_id, holder).start()
    started = time.monotonic()

    def settle(ok: bool, detail: str = "") -> None:
        try:
            if ok:
                ledger.settle_succeeded(usage_id, holder, measured_seconds=round(time.monotonic() - started, 3))
            else:
                ledger.settle_failed(usage_id, holder, error_code="INTERNAL", detail=detail, counts=False,
                                     terminal=True)
        except Exception as e:  # noqa: BLE001 - the sweeper settles a silent row
            logger.warning(f"vision figure: could not settle usage {usage_id}: {e}")

    try:
        payload = work()
    except BaseException as e:
        heartbeat.stop()
        settle(False, f"{type(e).__name__}: {e}")
        raise
    heartbeat.stop()
    settle(not payload.get("errors"), json.dumps(payload.get("errors") or {}))
    return payload


@celery_app.task(bind=True, max_retries=0, name=DESCRIBE_TASK,
                 time_limit=int(settings.conversion_figure_timeout_seconds) + 15,
                 soft_time_limit=int(settings.conversion_figure_timeout_seconds))
def describe_figure_task(self, job_id: str, sha256: str, object_name: str, describe: bool = True,
                         ocr: bool = False, caption_task: Optional[str] = None, usage_id: Optional[int] = None):
    """
    One unique figure of a conversion, on the vision worker: read the PNG from the
    results bucket, caption it and/or read its text, record the outcome. Never
    raises for a figure-level failure (the outcome says what failed).
    """
    outcome = {"description": None, "ocr_text": None}
    directory = Path(settings.temp_storage_path) / "figures" / str(job_id)
    image_path = directory / f"{sha256}.png"
    try:
        storage = _minio()
        data = storage.download_file(storage.bucket_results, object_name)
        if not data:
            raise FileNotFoundError(object_name)
        directory.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(data)
        outcome = _accounted(usage_id, lambda: describe_one(
            image_path, describe=describe, ocr=ocr, caption_task=fd.caption_task(caption_task)))
    except SoftTimeLimitExceeded:
        outcome = {**outcome, "error": "TIMEOUT"}
    except Exception as e:  # noqa: BLE001 - one figure, never the job
        logger.warning(f"[MAIN JOB {job_id}] Figure {sha256[:12]} failed: {type(e).__name__}: {e}")
        outcome = {**outcome, "error": type(e).__name__}
    finally:
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            pass
        record(job_id, sha256, outcome)
    return {"job_id": job_id, "sha256": sha256, "ok": not (outcome.get("error") or outcome.get("errors"))}


# ---------------------------------------------------------------------------
# Finishing the stage
# ---------------------------------------------------------------------------

def _results(job_id: str) -> Dict[str, dict]:
    raw = _redis().client.hgetall(fd.results_key(job_id)) or {}
    out = {}
    for key, value in raw.items():
        key = key.decode() if isinstance(key, bytes) else key
        try:
            out[key] = json.loads(value)
        except (TypeError, ValueError):
            continue
    return out


def _load_pending(job_id: str) -> dict:
    storage = _minio()
    raw = storage.download_file(storage.bucket_results, fd.pending_object(job_id))
    return json.loads(raw)


def _cleanup(job_id: str) -> None:
    """The temporary figure PNGs + pending.json, and the stage's Redis keys. Never raises."""
    try:
        storage = _minio()
        storage.delete_folder(storage.bucket_results, fd.figure_prefix(job_id))
    except Exception as e:  # noqa: BLE001 - DELETE /jobs/{id} and the purge remove them too
        logger.warning(f"[MAIN JOB {job_id}] Could not delete the temporary figures: {e}")
    try:
        _redis().client.delete(fd.results_key(job_id), fd.total_key(job_id))
    except Exception:  # noqa: BLE001 - they expire
        pass


def finalize(job_id: str, pending: dict, results: Dict[str, dict]) -> dict:
    """
    Inline the texts, complete the MAIN job (Redis result, Elasticsearch, MySQL),
    then delete the temporary figures and let purge_source run. Raises when the
    job could not be completed (the task retries, then fails the job).
    """
    from workers import tasks

    result = dict(pending["result"])
    markdown, counts, texts = fd.rewrite(result.get("markdown") or "", pending.get("entries") or [], results,
                                         describe=bool(pending.get("describe")), ocr=bool(pending.get("ocr")),
                                         max_chars=int(settings.conversion_figure_max_chars))
    metadata = dict(result.get("metadata") or {})
    metadata["words"] = len(markdown.split())
    metadata["figures"] = counts
    result.update({"markdown": markdown, "metadata": metadata, **counts})
    if result.get("assets") is not None:
        result["assets"] = fd.annotate_assets(result["assets"], texts)

    redis_client = _redis()
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if job is None or job.status != JobStatus.PROCESSING:
            db.rollback()
            logger.info(f"[MAIN JOB {job_id}] Describe stage discarded (job {getattr(job, 'status', None)})")
            _cleanup(job_id)
            return {"job_id": job_id, "status": "discarded"}
        user_id, filename = job.user_id, job.filename
        manifest = conversion_assets.manifest_of(job)
        if manifest is not None and pending.get("has_manifest"):
            job.assets_manifest = {**manifest, "assets": fd.annotate_assets(manifest.get("assets") or [], texts),
                                   "figures": counts}
        db.commit()

    redis_client.set_job_result(job_id, result)
    try:
        es_success = _es().store_job_result(
            job_id=job_id, markdown_content=markdown, user_id=user_id, filename=filename,
            total_pages=pending.get("total_pages") or metadata.get("pages"), metadata=metadata)
    except Exception as e:  # noqa: BLE001 - the Redis result serves it meanwhile
        logger.warning(f"[MAIN JOB {job_id}] Could not index the final markdown: {e}")
        es_success = False

    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if job is None or job.status != JobStatus.PROCESSING:
            db.rollback()
            _cleanup(job_id)
            return {"job_id": job_id, "status": "discarded"}
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        job.char_count = len(markdown)
        job.has_elasticsearch_result = es_success
        job.error_message = None
        db.commit()

    redis_client.set_job_status(job_id=job_id, job_type="main", status="completed", progress=100,
                                completed_at=datetime.utcnow())
    _cleanup(job_id)
    logger.info(f"[MAIN JOB {job_id}] Completed with figure texts: {counts}")
    # Settled only now, after the descriptions were inlined: purge_source applies
    tasks._remove_job_files(job_id)
    tasks._purge_source_if_requested(job_id)
    if pending.get("callback_url"):
        try:
            tasks.send_callback(pending["callback_url"], job_id, "completed", result)
        except Exception as e:  # noqa: BLE001 - the job is done
            logger.warning(f"[MAIN JOB {job_id}] Callback failed: {e}")
    return {"job_id": job_id, "status": "completed", **counts}


@celery_app.task(bind=True, max_retries=3, name=FINALIZE_TASK)
def finalize_figures_task(self, job_id: str, watchdog: bool = False, seen: int = 0):
    """
    Finish the describe stage once every figure reported (queued by the last
    vision task), or once nothing moved for CONVERSION_FIGURE_STALL_SECONDS
    (`watchdog`: re-armed while figures keep settling). Idempotent.
    """
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            status = job.status if job is not None else None
    except Exception as e:  # noqa: BLE001
        raise self.retry(exc=e, countdown=30)
    if status != JobStatus.PROCESSING:
        if status != JobStatus.PENDING:  # settled or deleted: nothing will read the figures any more
            _cleanup(job_id)
        return {"job_id": job_id, "status": "discarded"}

    try:
        results = _results(job_id)
        total = int(_redis().client.get(fd.total_key(job_id)) or 0)
    except Exception as e:  # noqa: BLE001 - Redis down: the watchdog comes back
        logger.warning(f"[MAIN JOB {job_id}] Describe stage state unavailable: {e}")
        if watchdog:
            finalize_figures_task.apply_async(kwargs={"job_id": job_id, "watchdog": True, "seen": seen},
                                              countdown=int(settings.conversion_figure_stall_seconds))
        return {"job_id": job_id, "status": "waiting"}

    done = len(results)
    if not total or done < total:
        if not watchdog:
            return {"job_id": job_id, "status": "waiting", "done": done, "total": total}
        if done > seen:
            finalize_figures_task.apply_async(kwargs={"job_id": job_id, "watchdog": True, "seen": done},
                                              countdown=int(settings.conversion_figure_stall_seconds))
            return {"job_id": job_id, "status": "waiting", "done": done, "total": total}
        logger.warning(f"[MAIN JOB {job_id}] Describe stage stalled at {done}/{total}: finishing without the rest")

    client = _redis().client
    try:
        if not client.set(fd.finalizing_key(job_id), "1", nx=True, ex=FINALIZE_LOCK_SECONDS):
            return {"job_id": job_id, "status": "finalizing"}
    except Exception:  # noqa: BLE001 - the row lock in finalize() still guards completion
        pass
    try:
        pending = _load_pending(job_id)
        return finalize(job_id, pending, results)
    except Exception as exc:
        logger.error(f"[MAIN JOB {job_id}] Describe stage could not finish: {exc}", exc_info=True)
        try:
            client.delete(fd.finalizing_key(job_id))
        except Exception:  # noqa: BLE001
            pass
        from workers import tasks

        if tasks._will_retry(self):
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        tasks._record_main_failure(job_id, _redis(), tasks._catalog_error("FIGURES_FAILED", exc), retrying=False)
        _cleanup(job_id)
        return {"job_id": job_id, "status": "failed"}
