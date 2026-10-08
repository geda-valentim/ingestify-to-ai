"""
The describe stage of a document conversion (`describe_images` / `ocr_images`;
shared/figure_descriptions.py has the pure parts).

    conversion (single document) / merge (split PDF)
        -> begin(): pending.json in MinIO, Job.figures_stage="describing", and the
           first figures dispatched; returns at once
    dispatch_next(): keeps at most CONVERSION_FIGURE_WINDOW figures of the job on
           the vision queue. Each one is placed when it is sent
           (dispatch.place_now on the `vision` feature, like the image routes and
           Full analysis): no route -> the vision queue as today; a route that
           cannot take it now -> tried again later with backoff (never skipped
           for being momentarily full)
    describe_figure_task (vision queue, LOW priority: interactive /images/* tasks
           are always taken first): caption and/or OCR of one unique image,
           outcome recorded in Redis, then the next figure is dispatched; the one
           that completes the set queues the finalize
    finalize_figures_task (default queue): rewrites the markdown, completes the
           MAIN job, then the post-completion steps (status, temporary files,
           purge_source, callback), retried on their own

No conversion worker ever waits on the vision worker: the stage is driven by
messages. The MAIN job stays PROCESSING (progress 90 -> 99) until the text is
inlined, so `has_pending_work` keeps purge_source away from the images the vision
worker reads; `Job.figures_stage_at` is the stage's heartbeat, read by the
stuck-job monitor instead of started_at and by the beat sweep (`sweep`).

Nothing here loses a good conversion: a figure that fails gets no text (counted in
`figures_skipped`); a stage that stalls (no figure settled for
CONVERSION_FIGURE_STALL_SECONDS while nothing of the job is in flight or the vision
queue is idle, or CONVERSION_FIGURE_MAX_STAGE_SECONDS in all) finishes with what it
has; a finalize that keeps failing completes the job with the figures as
placeholders. Only a pending.json that cannot be read at all fails the job.
"""
import json
import logging
import time
from datetime import datetime, timedelta
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
DISPATCH_TASK = "workers.tasks.dispatch_figures_task"
FINALIZE_TASK = "workers.tasks.finalize_figures_task"
# Celery priority of a figure on the vision queue (Redis transport: 0 is served
# first, 9 last; the interactive vision tasks carry none, i.e. 0)
FIGURE_PRIORITY = 9
STAGE_DESCRIBING = "describing"
STAGE_FINISHING = "finishing"
STAGE_PROGRESS_START = 90
STAGE_PROGRESS_SPAN = 9
FINALIZE_LOCK_SECONDS = 600
DISPATCH_BACKOFF_MAX_SECONDS = 300
# kombu's Redis transport keeps one list per priority step: "{queue}\x06\x16{step}"
_KOMBU_PRIORITY_SEP = "\x06\x16"


def _redis():
    from shared.redis_client import get_redis_client

    return get_redis_client()


def _minio():
    from shared.minio_client import get_minio_client

    return get_minio_client()


def _es():
    from shared.elasticsearch_client import get_es_client

    return get_es_client()


def _now() -> datetime:
    return datetime.utcnow()


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else value


# ---------------------------------------------------------------------------
# Durable marker (Job.figures_stage / figures_stage_at)
# ---------------------------------------------------------------------------

def touch(job_id: str) -> None:
    """Refresh the stage heartbeat (a figure dispatched, started or settled). Never raises."""
    try:
        with SessionLocal() as db:
            db.query(Job).filter(Job.id == job_id, Job.figures_stage == STAGE_DESCRIBING) \
                .update({Job.figures_stage_at: _now()}, synchronize_session=False)
            db.commit()
    except Exception as e:  # noqa: BLE001 - a missed heartbeat only makes the sweep look sooner
        logger.warning(f"[MAIN JOB {job_id}] Could not refresh the describe-stage heartbeat: {e}")


def _job_state(job_id: str):
    """(status, figures_stage, figures_stage_at, user_id) of the MAIN job; None when it is gone."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return None
        return job.status, job.figures_stage, job.figures_stage_at, job.user_id


def _describing(job_id: str) -> bool:
    try:
        state = _job_state(job_id)
    except Exception:  # noqa: BLE001 - unknown: let the work go on
        return True
    return state is not None and state[1] == STAGE_DESCRIBING


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
          has_manifest: bool = False) -> dict:
    """
    Start the describe stage of a converted document (`result`: markdown with the
    figure anchors, metadata, assets, and `figures`, the entries). Returns at once.

    Idempotent: a redelivered conversion / merge that reaches here again keeps the
    outcomes already recorded and only dispatches the figures still missing.
    """
    entries = list(result.pop("figures", None) or [])
    options = figure_options(job_id)
    work = fd.plan(entries, int(settings.conversion_figure_max_count))
    pending = {
        "result": result, "entries": entries, "work": work, "total_pages": total_pages,
        "callback_url": callback_url, "has_manifest": has_manifest,
        "describe": options["describe"], "ocr": options["ocr"],
        "caption_task": fd.caption_task(settings.conversion_figure_caption_task),
        "started": time.time(),
    }
    logger.info(f"[MAIN JOB {job_id}] Describe stage: {len(entries)} figures, {len(work)} unique to send "
                f"(describe={options['describe']}, ocr={options['ocr']})")
    if not _mark_describing(job_id):
        logger.info(f"[MAIN JOB {job_id}] Describe stage not started: the job is no longer processing")
        return {"job_id": job_id, "status": "discarded"}
    if not work or not (options["describe"] or options["ocr"]):
        return finalize(job_id, pending, {})

    redis_client = _redis()
    started = redis_client.client.get(fd.stage_key(job_id))
    if started:  # a redelivery: the stage keeps its clock and its recorded outcomes
        pending["started"] = json.loads(started).get("started") or pending["started"]
    storage = _minio()
    storage.upload_file(bucket_name=storage.bucket_results, object_name=fd.pending_object(job_id),
                        file_data=fd.dumps(pending).encode("utf-8"), content_type="application/json")
    _save_stage(job_id, pending)
    redis_client.update_job_progress(job_id, STAGE_PROGRESS_START + _progress_share(job_id),
                                     stage=STAGE_DESCRIBING, figures_total=len(work))
    dispatch_next(job_id)
    finalize_figures_task.apply_async(kwargs={"job_id": job_id, "watchdog": True},
                                      countdown=int(settings.conversion_figure_stall_seconds))
    return {"job_id": job_id, "status": "describing_figures", "figures": len(work)}


def _mark_describing(job_id: str) -> bool:
    """Job.figures_stage = describing, only for a job still PROCESSING (a redelivery of a
    settled job's merge must not reopen it)."""
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if job is None or job.status != JobStatus.PROCESSING or job.figures_stage not in (None, STAGE_DESCRIBING):
            db.rollback()
            return False
        job.figures_stage = STAGE_DESCRIBING
        job.figures_stage_at = _now()
        db.commit()
        return True


def _save_stage(job_id: str, pending: dict) -> None:
    """What dispatching needs, in Redis (pending.json in MinIO is the durable copy)."""
    client = _redis().client
    stage = {"work": pending["work"], "describe": pending["describe"], "ocr": pending["ocr"],
             "caption_task": pending["caption_task"], "started": pending.get("started")}
    client.set(fd.stage_key(job_id), fd.dumps(stage), ex=fd.RESULTS_TTL_SECONDS)
    client.set(fd.total_key(job_id), len(pending["work"]), ex=fd.RESULTS_TTL_SECONDS)


def _stage(job_id: str) -> dict:
    """The stage description (work list, options), from Redis, else from pending.json."""
    raw = _redis().client.get(fd.stage_key(job_id))
    if raw:
        return json.loads(raw)
    pending = _load_pending(job_id)
    _save_stage(job_id, pending)
    return {"work": pending["work"], "describe": pending["describe"], "ocr": pending["ocr"],
            "caption_task": pending["caption_task"], "started": pending.get("started")}


def _progress_share(job_id: str) -> int:
    try:
        client = _redis().client
        total = int(client.get(fd.total_key(job_id)) or 0)
        done = int(client.hlen(fd.results_key(job_id)) or 0)
        return int(min(done, total) / total * STAGE_PROGRESS_SPAN) if total else 0
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# Dispatching (bounded window, placed when sent)
# ---------------------------------------------------------------------------

def in_flight(job_id: str) -> set:
    """Figures sent to the vision worker that have not reported yet."""
    client = _redis().client
    sent = {_text(s) for s in (client.hkeys(fd.sent_key(job_id)) or [])}
    done = {_text(d) for d in (client.hkeys(fd.results_key(job_id)) or [])}
    return sent - done


def _place(job_id: str, user_id: Optional[str], sha256: str):
    from shared.engines import dispatch as engine_dispatch

    try:
        from shared.iam.remote import remote_use_of

        return engine_dispatch.place_now(
            feature="vision", subject_id=f"{job_id}:{sha256[:16]}", job_id=job_id, user_id=user_id,
            remote_use=remote_use_of(user_id, session_factory=SessionLocal), session_factory=SessionLocal)
    except Exception as e:  # noqa: BLE001 - routing never fails what would run without it
        logger.warning(f"[MAIN JOB {job_id}] Vision placement failed, using the vision queue: {e}")
        return engine_dispatch.Placement("today")


def _send(kwargs: dict, usage_id: Optional[int]) -> None:
    from shared.engines import dispatch as engine_dispatch

    if usage_id is None:
        describe_figure_task.apply_async(kwargs=kwargs, priority=FIGURE_PRIORITY)
        return
    kwargs = {**kwargs, "usage_id": usage_id}
    engine_dispatch.publish_sync(SessionLocal, usage_id,
                                 lambda: describe_figure_task.apply_async(kwargs=kwargs, priority=FIGURE_PRIORITY))


def _schedule_retry(job_id: str) -> int:
    """Try the dispatch again later, with backoff (one scheduled tick per job)."""
    client = _redis().client
    attempt = int(client.incr(fd.backoff_key(job_id)) or 1)
    client.expire(fd.backoff_key(job_id), fd.RESULTS_TTL_SECONDS)
    countdown = min(10 * (2 ** min(attempt - 1, 6)), DISPATCH_BACKOFF_MAX_SECONDS)
    if client.set(fd.tick_key(job_id), "1", nx=True, ex=countdown):
        dispatch_figures_task.apply_async(kwargs={"job_id": job_id}, countdown=countdown)
    return countdown


def dispatch_next(job_id: str) -> int:
    """
    Send figures until CONVERSION_FIGURE_WINDOW of this job are in flight. Each is
    placed right before it is sent; a route that cannot take it now schedules a
    retry with backoff instead. Returns how many were sent. Never raises.
    """
    try:
        state = _job_state(job_id)
        if state is None or state[1] != STAGE_DESCRIBING:
            return 0
        stage = _stage(job_id)
        user_id = state[3]
        client = _redis().client
        window = max(1, int(settings.conversion_figure_window))
        free = window - len(in_flight(job_id))
        done = {_text(d) for d in (client.hkeys(fd.results_key(job_id)) or [])}
        sent_count = 0
        for item in stage["work"]:
            if free <= 0:
                break
            sha = item["sha256"]
            if sha in done or not client.hsetnx(fd.sent_key(job_id), sha, int(time.time())):
                continue
            client.expire(fd.sent_key(job_id), fd.RESULTS_TTL_SECONDS)
            placement = _place(job_id, user_id, sha)
            if placement.outcome not in ("placed", "today"):
                # Nothing can take it right now: not a failure of the figure
                client.hdel(fd.sent_key(job_id), sha)
                countdown = _schedule_retry(job_id)
                logger.info(f"[MAIN JOB {job_id}] No vision engine free ({placement.reason}); "
                            f"figures retried in {countdown}s")
                break
            kwargs = {"job_id": job_id, "sha256": sha, "object_name": item["object"],
                      "describe": stage["describe"], "ocr": stage["ocr"], "caption_task": stage["caption_task"]}
            try:
                _send(kwargs, placement.usage_id if placement.outcome == "placed" else None)
            except Exception as e:  # noqa: BLE001 - broker down: retried later
                client.hdel(fd.sent_key(job_id), sha)
                logger.warning(f"[MAIN JOB {job_id}] Could not queue figure {sha[:12]}: {e}")
                _schedule_retry(job_id)
                break
            client.delete(fd.backoff_key(job_id))
            free -= 1
            sent_count += 1
        if sent_count:
            touch(job_id)
        return sent_count
    except Exception as e:  # noqa: BLE001 - the watchdog / beat sweep take over
        logger.warning(f"[MAIN JOB {job_id}] Could not dispatch figures: {e}")
        return 0


@celery_app.task(bind=True, max_retries=0, name=DISPATCH_TASK)
def dispatch_figures_task(self, job_id: str):
    """A backed-off dispatch of the describe stage (a route was full, the broker was down)."""
    try:
        _redis().client.delete(fd.tick_key(job_id))
    except Exception:  # noqa: BLE001
        pass
    return {"job_id": job_id, "sent": dispatch_next(job_id)}


# ---------------------------------------------------------------------------
# The vision side
# ---------------------------------------------------------------------------

def record(job_id: str, sha256: str, outcome: dict) -> int:
    """
    Store one image's outcome, dispatch the next figure, and queue the finalize once
    the set is complete. A stage already cleaned up is not recreated. Never raises.
    """
    try:
        redis_client = _redis()
        client = redis_client.client
        if not client.exists(fd.total_key(job_id)):
            return 0  # finished (or deleted) meanwhile: nothing to record into
        client.hset(fd.results_key(job_id), sha256, fd.dumps(outcome))
        client.expire(fd.results_key(job_id), fd.RESULTS_TTL_SECONDS)
        done = int(client.hlen(fd.results_key(job_id)) or 0)
        total = int(client.get(fd.total_key(job_id)) or 0)
        touch(job_id)
        if total:
            share = min(done, total) / total
            redis_client.update_job_progress(job_id, STAGE_PROGRESS_START + int(share * STAGE_PROGRESS_SPAN),
                                             stage=STAGE_DESCRIBING, figures_done=min(done, total),
                                             figures_total=total)
        if total and done >= total:
            celery_app.send_task(FINALIZE_TASK, kwargs={"job_id": job_id})
        else:
            dispatch_next(job_id)
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


def _release(usage_id: Optional[int]) -> None:
    if usage_id is None:
        return
    from shared.engines import dispatch as engine_dispatch

    engine_dispatch.release_sync(SessionLocal, usage_id, "JOB_SETTLED")


@celery_app.task(bind=True, max_retries=0, name=DESCRIBE_TASK, priority=FIGURE_PRIORITY,
                 time_limit=int(settings.conversion_figure_timeout_seconds) + 15,
                 soft_time_limit=int(settings.conversion_figure_timeout_seconds))
def describe_figure_task(self, job_id: str, sha256: str, object_name: str, describe: bool = True,
                         ocr: bool = False, caption_task: Optional[str] = None, usage_id: Optional[int] = None):
    """
    One unique figure of a conversion, on the vision worker: read the PNG from the
    results bucket, caption it and/or read its text, record the outcome. Skipped
    (nothing recorded, no inference) when the job left the describe stage. Never
    raises for a figure-level failure (the outcome says what failed).
    """
    if not _describing(job_id):
        _release(usage_id)
        logger.info(f"[MAIN JOB {job_id}] Figure {sha256[:12]} skipped: the job left the describe stage")
        return {"job_id": job_id, "sha256": sha256, "ok": False, "skipped": True}
    touch(job_id)
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
        try:
            out[_text(key)] = json.loads(value)
        except (TypeError, ValueError):
            continue
    return out


def _load_pending(job_id: str) -> dict:
    storage = _minio()
    raw = storage.download_file(storage.bucket_results, fd.pending_object(job_id))
    return json.loads(raw)


def cleanup(job_id: str) -> None:
    """The temporary figure PNGs + pending.json, and the stage's Redis keys. Never raises."""
    try:
        storage = _minio()
        storage.delete_folder(storage.bucket_results, fd.figure_prefix(job_id))
    except Exception as e:  # noqa: BLE001 - the settle hook and DELETE /jobs/{id} remove them too
        logger.warning(f"[MAIN JOB {job_id}] Could not delete the temporary figures: {e}")
    try:
        _redis().client.delete(*fd.stage_keys(job_id))
    except Exception:  # noqa: BLE001 - they expire
        pass


def vision_queue_busy() -> bool:
    """Is anything waiting on the vision queue (any priority)? Unknown reads as busy."""
    try:
        client = _redis().client
        queue = settings.vision_queue
        names = [queue] + [f"{queue}{_KOMBU_PRIORITY_SEP}{step}" for step in range(1, 10)]
        return any(int(client.llen(name) or 0) for name in names)
    except Exception:  # noqa: BLE001
        return True


def stall_reason(job_id: str, figures_stage_at: Optional[datetime], started: Optional[float]) -> Optional[str]:
    """
    Why the stage should finish now with what it has, or None (keep waiting):
    "deadline" past CONVERSION_FIGURE_MAX_STAGE_SECONDS; "stalled" when no figure
    moved for CONVERSION_FIGURE_STALL_SECONDS and nothing of the job is in flight, or
    the vision queue is idle (a lost task). Figures merely waiting behind a busy
    vision queue extend the stage (and its heartbeat).
    """
    now = _now()
    if started and time.time() - float(started) > int(settings.conversion_figure_max_stage_seconds):
        return "deadline"
    last = figures_stage_at or now
    if (now - last).total_seconds() < int(settings.conversion_figure_stall_seconds):
        return None
    if not in_flight(job_id) or not vision_queue_busy():
        return "stalled"
    touch(job_id)  # legitimately queued behind other vision work
    return None


def finalize(job_id: str, pending: dict, results: Dict[str, dict], *, reason: Optional[str] = None) -> dict:
    """
    Inline the texts and complete the MAIN job (Redis result, Elasticsearch,
    MySQL), then the post-completion steps. Raises when the job could not be
    completed (the caller degrades). A job FAILED by someone else while its stage
    was describing is completed all the same: the conversion itself succeeded.
    """
    result = dict(pending["result"])
    markdown, counts, texts = fd.rewrite(result.get("markdown") or "", pending.get("entries") or [], results,
                                         describe=bool(pending.get("describe")), ocr=bool(pending.get("ocr")),
                                         max_chars=int(settings.conversion_figure_max_chars))
    metadata = dict(result.get("metadata") or {})
    metadata["words"] = len(markdown.split())
    metadata["figures"] = {**counts, **({"reason": reason} if reason else {})}
    result.update({"markdown": markdown, "metadata": metadata, **counts})
    if result.get("assets") is not None:
        result["assets"] = fd.annotate_assets(result["assets"], texts)

    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if not _finishable(job):
            db.rollback()
            logger.info(f"[MAIN JOB {job_id}] Describe stage discarded (job {getattr(job, 'status', None)})")
            if job is None or job.status == JobStatus.CANCELLED:
                cleanup(job_id)
            return {"job_id": job_id, "status": "discarded"}
        user_id, filename = job.user_id, job.filename
        manifest = conversion_assets.manifest_of(job)
        if manifest is not None and pending.get("has_manifest"):
            job.assets_manifest = {**manifest, "assets": fd.annotate_assets(manifest.get("assets") or [], texts),
                                   "figures": counts}
        db.commit()

    _redis().set_job_result(job_id, result)
    try:
        es_success = _es().store_job_result(
            job_id=job_id, markdown_content=markdown, user_id=user_id, filename=filename,
            total_pages=pending.get("total_pages") or metadata.get("pages"), metadata=metadata)
    except Exception as e:  # noqa: BLE001 - the Redis result serves it meanwhile
        logger.warning(f"[MAIN JOB {job_id}] Could not index the final markdown: {e}")
        es_success = False

    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if not _finishable(job):
            db.rollback()
            return {"job_id": job_id, "status": "discarded"}
        job.status = JobStatus.COMPLETED
        job.completed_at = _now()
        job.char_count = len(markdown)
        job.has_elasticsearch_result = es_success
        job.error_message = None
        job.figures_stage = STAGE_FINISHING
        job.figures_stage_at = _now()
        db.commit()
    logger.info(f"[MAIN JOB {job_id}] Completed with figure texts: {counts}" + (f" ({reason})" if reason else ""))
    after_complete(job_id, callback_url=pending.get("callback_url"), result=result)
    return {"job_id": job_id, "status": "completed", **counts}


def _finishable(job: Optional[Job]) -> bool:
    return job is not None and job.figures_stage == STAGE_DESCRIBING and \
        job.status in (JobStatus.PROCESSING, JobStatus.FAILED)


def after_complete(job_id: str, *, callback_url: Optional[str] = None, result: Optional[dict] = None) -> bool:
    """
    The steps after the COMPLETED commit, each idempotent and on its own: the Redis
    status, the temporary files, purge_source (settled only now, after the texts
    were inlined), the callback (once). The marker goes back to NULL once they all
    ran; a step that failed leaves it at "finishing" for the next finalize / beat
    sweep to run them again (never the finalize itself). Returns whether all ran.
    """
    from workers import tasks

    ok = True
    steps = [
        ("status", lambda: _redis().set_job_status(job_id=job_id, job_type="main", status="completed",
                                                   progress=100, completed_at=_now())),
        ("cleanup", lambda: cleanup(job_id)),
        ("files", lambda: tasks._remove_job_files(job_id)),
        ("purge", lambda: tasks._purge_source_if_requested(job_id)),
    ]
    if callback_url:
        steps.append(("callback", lambda: tasks.send_callback(
            callback_url, job_id, "completed", result or _redis().get_job_result(job_id))))
    for name, step in steps:
        try:
            step()
        except Exception as e:  # noqa: BLE001 - retried by the next finalize / sweep (not the callback)
            logger.warning(f"[MAIN JOB {job_id}] Post-completion step {name} failed: {e}")
            if name != "callback":
                ok = False
    if ok:
        try:
            with SessionLocal() as db:
                db.query(Job).filter(Job.id == job_id, Job.figures_stage == STAGE_FINISHING) \
                    .update({Job.figures_stage: None, Job.figures_stage_at: _now()}, synchronize_session=False)
                db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[MAIN JOB {job_id}] Could not clear the describe-stage marker: {e}")
            ok = False
    return ok


def degrade(job_id: str, reason: str) -> dict:
    """
    The finalize kept failing: complete the job with every figure as a placeholder
    (all counted in figures_skipped), so a describe failure never loses a good
    conversion. Only a pending.json that cannot be read fails the job.
    """
    from workers import tasks

    try:
        pending = _load_pending(job_id)
    except Exception as e:  # noqa: BLE001 - nothing to complete with
        logger.error(f"[MAIN JOB {job_id}] Describe stage lost its pending result: {e}")
        tasks._record_main_failure(job_id, _redis(), tasks._catalog_error("FIGURES_FAILED", e), retrying=False)
        return {"job_id": job_id, "status": "failed"}
    return finalize(job_id, {**pending, "describe": False, "ocr": False}, {}, reason=reason)


def force_finish(job_id: str, reason: Optional[str]) -> dict:
    """
    Finish a describing stage now with the outcomes recorded so far (all reported,
    the watchdog, the stuck-job monitor). One at a time per job. A finalize that
    raises degrades to the placeholders. Never raises.
    """
    try:
        client = _redis().client
        if not client.set(fd.finalizing_key(job_id), "1", nx=True, ex=FINALIZE_LOCK_SECONDS):
            return {"job_id": job_id, "status": "finalizing"}
    except Exception:  # noqa: BLE001 - the row lock in finalize() still guards completion
        client = None
    try:
        try:
            results = _results(job_id)
        except Exception:  # noqa: BLE001 - Redis down: every figure skipped
            results = {}
        try:
            return finalize(job_id, _load_pending(job_id), results, reason=reason)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[MAIN JOB {job_id}] Describe stage could not finish ({reason}): {e}", exc_info=True)
            try:
                return degrade(job_id, f"{reason or 'complete'}; finalize_failed")
            except Exception as e2:  # noqa: BLE001 - the beat sweep comes back to it
                logger.error(f"[MAIN JOB {job_id}] Describe stage could not degrade: {e2}", exc_info=True)
                return {"job_id": job_id, "status": "error"}
    finally:
        if client is not None:
            try:
                client.delete(fd.finalizing_key(job_id))
            except Exception:  # noqa: BLE001
                pass


@celery_app.task(bind=True, max_retries=8, name=FINALIZE_TASK)
def finalize_figures_task(self, job_id: str, watchdog: bool = False):
    """
    Finish the describe stage once every figure reported (queued by the last
    vision task), or, as the watchdog, once it stalled (`stall_reason`); also runs
    again the post-completion steps of a job left "finishing". Idempotent; the beat
    sweep (`sweep`) re-arms it when its own chain broke (a long DB outage).
    """
    try:
        state = _job_state(job_id)
    except Exception as e:  # noqa: BLE001 - DB down: back off; the beat sweep re-arms anyway
        raise self.retry(exc=e, countdown=min(60 * (2 ** self.request.retries), 1800))
    if state is None:
        cleanup(job_id)
        return {"job_id": job_id, "status": "discarded"}
    status, stage, stage_at, _user = state
    if stage == STAGE_FINISHING and status == JobStatus.COMPLETED:
        after_complete(job_id)
        return {"job_id": job_id, "status": "completed"}
    if stage != STAGE_DESCRIBING or status not in (JobStatus.PROCESSING, JobStatus.FAILED):
        if status == JobStatus.CANCELLED:
            cleanup(job_id)
        return {"job_id": job_id, "status": "discarded"}

    try:
        client = _redis().client
        done = int(client.hlen(fd.results_key(job_id)) or 0)
        total = int(client.get(fd.total_key(job_id)) or 0)
        started = (_stage(job_id) or {}).get("started")
    except Exception as e:  # noqa: BLE001 - Redis / MinIO down: the watchdog comes back
        logger.warning(f"[MAIN JOB {job_id}] Describe stage state unavailable: {e}")
        if watchdog:
            finalize_figures_task.apply_async(kwargs={"job_id": job_id, "watchdog": True},
                                              countdown=int(settings.conversion_figure_stall_seconds))
        return {"job_id": job_id, "status": "waiting"}

    reason = None
    if not total or done < total:
        if not watchdog:
            return {"job_id": job_id, "status": "waiting", "done": done, "total": total}
        reason = stall_reason(job_id, stage_at, started)
        if reason is None:
            finalize_figures_task.apply_async(kwargs={"job_id": job_id, "watchdog": True},
                                              countdown=int(settings.conversion_figure_stall_seconds))
            return {"job_id": job_id, "status": "waiting", "done": done, "total": total}
        logger.warning(f"[MAIN JOB {job_id}] Describe stage {reason} at {done}/{total}: finishing without the rest")
    elif status == JobStatus.FAILED:
        reason = "failed_meanwhile"
    return force_finish(job_id, reason)


def sweep(limit: int = 50) -> int:
    """
    Beat: re-arm the watchdog of describe stages whose heartbeat is older than
    CONVERSION_FIGURE_STALL_SECONDS (its countdown chain may have died), and run
    again the post-completion steps of jobs left "finishing". Returns how many.
    """
    now = _now()
    stale = now - timedelta(seconds=int(settings.conversion_figure_stall_seconds))
    try:
        with SessionLocal() as db:
            rows = db.query(Job.id).filter(
                ((Job.figures_stage == STAGE_DESCRIBING) & (Job.figures_stage_at < stale))
                | ((Job.figures_stage == STAGE_FINISHING) & (Job.figures_stage_at < now - timedelta(minutes=5)))
            ).limit(limit).all()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[FIGURES] Could not list stalled describe stages: {e}")
        return 0
    for (job_id,) in rows:
        try:
            finalize_figures_task.apply_async(kwargs={"job_id": job_id, "watchdog": True})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[FIGURES] Could not re-arm the watchdog of {job_id}: {e}")
    return len(rows)
