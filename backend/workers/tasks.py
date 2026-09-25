"""
Tasks Celery com arquitetura hierárquica de jobs

Hierarquia:
  MAIN JOB
    ├─> SPLIT JOB (divide PDF)
    ├─> PAGE JOB 1, 2, 3... (processa páginas em paralelo)
    └─> MERGE JOB (combina resultados)
"""

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from pathlib import Path
from datetime import datetime
from uuid import uuid4
import json
import logging
import asyncio
import shutil

from workers.celery_app import celery_app
from workers.converter import get_converter
from workers.sources import get_source_handler
from shared.redis_client import get_redis_client
from shared.elasticsearch_client import get_es_client
from shared.minio_client import get_minio_client
from shared.database import SessionLocal
from shared.models import Job, Page, JobStatus
from shared.config import get_settings
from shared.pdf_splitter import PDFSplitter, should_split_pdf
from shared.transcripts import TRANSCRIPT_CONTENT_TYPES, transcript_object_name

logger = logging.getLogger(__name__)
settings = get_settings()


def _resolve_uploaded_file(source: str, job_id: str) -> Path:
    """
    Resolve the path of a file uploaded through the API for this job.

    Only files the API saved under {temp}/uploads/{job_id}/ or {temp}/audio/{job_id}/
    are accepted, so a crafted `source` cannot make the worker read arbitrary
    local files (other users' uploads, container files) and return their content.
    """
    if not source:
        raise ValueError("Missing uploaded file path")

    file_path = Path(source).resolve()
    base = Path(settings.temp_storage_path).resolve()
    allowed_dirs = [base / "uploads" / job_id, base / "audio" / job_id]

    if not any(file_path.is_relative_to(d) for d in allowed_dirs):
        logger.warning(f"[MAIN JOB {job_id}] Rejected file source outside upload dir: {source}")
        raise ValueError("Invalid uploaded file path")

    return file_path


def _remove_job_files(job_id: str) -> None:
    """
    Delete a finished job's local files: work dir, uploaded file and audio.

    The original upload is kept in MinIO (page retries restore it from there),
    so nothing is needed on disk once the job completed. Failed jobs keep their
    files for Celery retries; the periodic cleanup_stale_files task removes them.
    """
    base = Path(settings.temp_storage_path)
    for directory in (base / job_id, base / "uploads" / job_id, base / "audio" / job_id):
        try:
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
        except Exception as e:
            logger.warning(f"[JOB {job_id}] Could not remove {directory}: {e}")


# ============================================
# MAIN JOB - Ponto de entrada
# ============================================

@celery_app.task(bind=True, max_retries=3)
def process_conversion(
    self,
    job_id: str,
    source_type: str,
    source: str,
    options: dict = None,
    callback_url: str = None,
    auth_token: str = None,
):
    """
    Main job - processa conversão de documento

    Args:
        job_id: MAIN job ID
        source_type: Tipo de fonte (file, url, gdrive, dropbox)
        source: Fonte do documento
        options: Opções de conversão
        callback_url: Webhook opcional
        auth_token: Token de autenticação
    """
    if options is None:
        options = {}

    redis_client = get_redis_client()
    es_client = get_es_client()

    # Get preset from options
    preset = options.get('docling_preset') if options else None
    converter = get_converter(preset=preset)

    logger.info(f"[MAIN JOB {job_id}] Starting conversion: {source_type} (preset={preset})")

    # Update MySQL: Set job to processing
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.error(f"[MAIN JOB {job_id}] MySQL update error: {e}")
    finally:
        db.close()

    try:
        # Update main job status in Redis
        redis_client.set_job_status(
            job_id=job_id,
            job_type="main",
            status="processing",
            progress=10,
            started_at=datetime.utcnow(),
        )

        # 1. Download file (10% -> 20%)
        logger.info(f"[MAIN JOB {job_id}] Downloading from {source_type}...")
        handler = get_source_handler(source_type)

        temp_dir = Path(settings.temp_storage_path) / job_id
        temp_dir.mkdir(parents=True, exist_ok=True)

        if source_type == 'file':
            file_path = _resolve_uploaded_file(source, job_id)
        else:
            file_path = asyncio.run(
                handler.download(
                    source=source,
                    temp_path=temp_dir,
                    auth_token=auth_token
                )
            )

        logger.info(f"[MAIN JOB {job_id}] File downloaded: {file_path}")
        redis_client.update_job_progress(job_id, 20)

        # 2. Check if this is an audio file for transcription
        is_audio = options.get('is_audio', False) or source_type == 'audio'
        audio_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus', '.webm', '.wma', '.aac', '.oga', '.spx']
        file_ext = file_path.suffix.lower()

        if is_audio or file_ext in audio_extensions:
            logger.info(f"[MAIN JOB {job_id}] Audio file detected - transcribing with Whisper")

            try:
                from workers.audio import transcribe_with_gpu_fallback

                provider_override = options.get('transcriber_provider')

                # Update progress
                redis_client.update_job_progress(job_id, 30)

                # Transcribe audio
                transcription_options = {
                    'language': options.get('audio_language') or options.get('language'),
                    'include_word_timestamps': options.get('include_word_timestamps', False),
                    'temperature': options.get('temperature', 0.0),
                    'beam_size': options.get('beam_size', 5)
                }

                # Uses the GPU when available (detected once per worker) and falls back to CPU
                result, transcriber = transcribe_with_gpu_fallback(
                    file_path, transcription_options, force_provider=provider_override
                )

                logger.info(
                    f"[MAIN JOB {job_id}] Transcription complete with {transcriber.__class__.__name__} "
                    f"on {result.get('device')}: {result['word_count']} words, "
                    f"{result['duration']:.2f}s, language={result['language']}"
                )
                redis_client.update_job_progress(job_id, 70)

                # Format as markdown
                include_timestamps = options.get('include_timestamps', True)
                markdown_content = transcriber.format_as_markdown(result, include_timestamps)

                # Subtitle / text outputs, retrievable via GET /jobs/{id}/result?format=...
                transcript_outputs = {
                    'vtt': transcriber.format_as_vtt(result),
                    'srt': transcriber.format_as_srt(result),
                    'txt': transcriber.format_as_text(result),
                    'json': json.dumps(
                        {k: result.get(k) for k in ('language', 'duration', 'text', 'segments')},
                        ensure_ascii=False,
                    ),
                }
                _store_transcript_outputs(job_id, transcript_outputs)

                # Store result in Redis
                result_with_markdown = {
                    'markdown': markdown_content,
                    'metadata': {
                        'format': file_path.suffix.lower().lstrip('.') or options.get('media_kind', 'audio'),
                        'size_bytes': file_path.stat().st_size,
                        'words': result['word_count'],
                        'language': result['language'],
                        'duration': result['duration'],
                        'word_count': result['word_count'],
                        'char_count': result['char_count'],
                        'provider': result.get('provider', 'unknown'),
                        'model': result.get('model', 'unknown'),
                        'device': result.get('device'),
                        'output_format': options.get('output_format', 'markdown'),
                        'available_formats': ['markdown'] + list(transcript_outputs),
                    },
                    'transcript': transcript_outputs,
                }
                redis_client.set_job_result(job_id, result_with_markdown)
                redis_client.update_job_progress(job_id, 80)

                # Store result in Elasticsearch
                db = SessionLocal()
                try:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    filename = job.filename if job else None
                    user_id = job.user_id if job else None
                finally:
                    db.close()

                es_success = es_client.store_job_result(
                    job_id=job_id,
                    markdown_content=markdown_content,
                    user_id=user_id,
                    filename=filename,
                    total_pages=None,  # Audio files don't have pages
                    metadata=result_with_markdown['metadata']
                )

                if es_success:
                    logger.info(f"[MAIN JOB {job_id}] Result stored in Elasticsearch")
                else:
                    logger.warning(f"[MAIN JOB {job_id}] Failed to store result in Elasticsearch")

                redis_client.update_job_progress(job_id, 90)

                # Update MySQL with completion
                db = SessionLocal()
                try:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job:
                        job.status = JobStatus.COMPLETED
                        job.completed_at = datetime.utcnow()
                        job.char_count = result['char_count']
                        job.has_elasticsearch_result = es_success
                        db.commit()
                        logger.info(f"[MAIN JOB {job_id}] MySQL updated with completion")
                except Exception as e:
                    logger.error(f"[MAIN JOB {job_id}] MySQL update error: {e}")
                finally:
                    db.close()

                # Mark as completed
                redis_client.set_job_status(
                    job_id=job_id,
                    job_type="main",
                    status="completed",
                    progress=100,
                    completed_at=datetime.utcnow()
                )

                _remove_job_files(job_id)
                logger.info(f"[MAIN JOB {job_id}] ✓ Audio transcription completed successfully")
                return

            except Exception as e:
                logger.error(f"[MAIN JOB {job_id}] Audio transcription failed: {e}", exc_info=True)

                # Update Redis
                redis_client.set_job_status(
                    job_id=job_id,
                    job_type="main",
                    status="failed",
                    progress=0,
                    error=str(e),
                    completed_at=datetime.utcnow()
                )

                # Update MySQL
                db = SessionLocal()
                try:
                    job = db.query(Job).filter(Job.id == job_id).first()
                    if job:
                        job.status = JobStatus.FAILED
                        job.error_message = str(e)
                        job.completed_at = datetime.utcnow()
                        db.commit()
                except Exception as db_error:
                    logger.error(f"[MAIN JOB {job_id}] MySQL update error: {db_error}")
                finally:
                    db.close()

                logger.error(f"[MAIN JOB {job_id}] ✗ Audio transcription failed")
                raise

        # 3. Check if PDF needs splitting
        if should_split_pdf(file_path, min_pages=2):
            logger.info(f"[MAIN JOB {job_id}] PDF multi-page detected - creating split job")

            # Create SPLIT JOB
            split_job_id = str(uuid4())
            split_pdf_task.delay(
                split_job_id=split_job_id,
                parent_job_id=job_id,
                file_path=str(file_path),
                options=options
            )

            # Add split job as child
            redis_client.add_child_job(job_id, "split", split_job_id)

            logger.info(f"[MAIN JOB {job_id}] Split job created: {split_job_id}")

            # Main job agora espera os child jobs completarem
            # Progress será atualizado pelos page jobs

        else:
            # Documento não-PDF ou PDF single page - processar direto
            logger.info(f"[MAIN JOB {job_id}] Single document - converting directly")

            result = converter.convert_to_markdown(file_path, options)

            logger.info(f"[MAIN JOB {job_id}] Conversion complete")
            redis_client.update_job_progress(job_id, 80)

            # Store result in Redis
            redis_client.set_job_result(job_id, result)
            redis_client.update_job_progress(job_id, 90)

            # Store result in Elasticsearch
            markdown_content = result.get("markdown", "")
            metadata = result.get("metadata", {})

            db = SessionLocal()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                filename = job.filename if job else None
                user_id = job.user_id if job else None
            finally:
                db.close()

            es_success = es_client.store_job_result(
                job_id=job_id,
                markdown_content=markdown_content,
                user_id=user_id,
                filename=filename,
                total_pages=metadata.get("pages"),
                metadata=metadata
            )

            # Update MySQL: Mark job as completed
            db = SessionLocal()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.utcnow()
                    job.char_count = len(markdown_content)
                    job.has_elasticsearch_result = es_success
                    db.commit()
            except Exception as e:
                logger.error(f"[MAIN JOB {job_id}] MySQL completion error: {e}")
            finally:
                db.close()

            # Cleanup (work dir and the uploaded file; the original stays in MinIO)
            _remove_job_files(job_id)

            # Mark as completed in Redis
            redis_client.set_job_status(
                job_id=job_id,
                job_type="main",
                status="completed",
                progress=100,
                completed_at=datetime.utcnow(),
            )

            logger.info(f"[MAIN JOB {job_id}] Completed successfully")

            # Callback
            if callback_url:
                send_callback(callback_url, job_id, "completed", result)

        return {"job_id": job_id, "status": "completed"}

    except SoftTimeLimitExceeded:
        # Gracefully handle soft timeout - mark as failed and retry
        logger.warning(f"[MAIN JOB {job_id}] Soft timeout exceeded - marking as failed for retry")

        error_msg = f"Task exceeded soft time limit ({settings.conversion_timeout_seconds - 30}s)"

        # Update Redis
        redis_client.set_job_status(
            job_id=job_id,
            job_type="main",
            status="failed",
            progress=0,
            error=error_msg,
            completed_at=datetime.utcnow(),
        )

        # Update MySQL
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = error_msg
                job.completed_at = datetime.utcnow()
                db.commit()
        except Exception as e:
            logger.error(f"[MAIN JOB {job_id}] MySQL update error on timeout: {e}")
        finally:
            db.close()

        # Cleanup temp files
        try:
            temp_dir = Path(settings.temp_storage_path) / job_id
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        # Retry with backoff
        raise self.retry(countdown=60 * (2 ** self.request.retries))

    except Exception as exc:
        logger.error(f"[MAIN JOB {job_id}] Failed: {exc}", exc_info=True)

        # Update Redis
        redis_client.set_job_status(
            job_id=job_id,
            job_type="main",
            status="failed",
            progress=0,
            error=str(exc),
            completed_at=datetime.utcnow(),
        )

        # Update MySQL: Mark job as failed
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                job.completed_at = datetime.utcnow()
                db.commit()
        except Exception as e:
            logger.error(f"[MAIN JOB {job_id}] MySQL failure error: {e}")
        finally:
            db.close()

        # Cleanup on failure
        try:
            temp_dir = Path(settings.temp_storage_path) / job_id
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ============================================
# SPLIT JOB - Divide PDF em páginas
# ============================================

@celery_app.task(bind=True, max_retries=2)
def split_pdf_task(
    self,
    split_job_id: str,
    parent_job_id: str,
    file_path: str,
    options: dict = None,
):
    """
    Split job - divide PDF em páginas individuais

    Args:
        split_job_id: ID deste split job
        parent_job_id: ID do main job
        file_path: Caminho do PDF
        options: Opções de conversão
    """
    if options is None:
        options = {}

    redis_client = get_redis_client()

    logger.info(f"[SPLIT JOB {split_job_id}] Starting PDF split")

    try:
        # Mark split job as processing in Redis
        redis_client.set_job_status(
            job_id=split_job_id,
            job_type="split",
            status="processing",
            parent_job_id=parent_job_id,
            started_at=datetime.utcnow(),
        )

        # Split PDF
        temp_dir = Path(settings.temp_storage_path) / parent_job_id / "pages"
        splitter = PDFSplitter(temp_dir)
        page_files = splitter.split_pdf(Path(file_path), job_id=parent_job_id)

        total_pages = len(page_files)
        logger.info(f"[SPLIT JOB {split_job_id}] PDF split into {total_pages} pages")

        # Store total pages in parent job (Redis)
        redis_client.set_job_pages(parent_job_id, total_pages)

        # Update MySQL: Update parent job with total_pages
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == parent_job_id).first()
            if job:
                job.total_pages = total_pages
                db.commit()
        except Exception as e:
            logger.error(f"[SPLIT JOB {split_job_id}] MySQL update error: {e}")
        finally:
            db.close()

        # Create PAGE records in MySQL and PAGE JOBS for each page
        for page_num, page_file_path, minio_path in page_files:
            page_job_id = str(uuid4())

            logger.info(f"[SPLIT JOB {split_job_id}] Creating page job {page_job_id} for page {page_num}")

            # Create Page record in MySQL
            db = SessionLocal()
            try:
                from shared.models import Page as PageModel
                page = PageModel(
                    id=str(uuid4()),
                    job_id=parent_job_id,
                    page_number=page_num,
                    page_job_id=page_job_id,
                    minio_page_path=minio_path,
                    status=JobStatus.PENDING
                )
                db.add(page)
                db.commit()
            except Exception as e:
                logger.error(f"[SPLIT JOB {split_job_id}] MySQL page creation error: {e}")
            finally:
                db.close()

            # Launch page conversion task
            convert_page_task.delay(
                page_job_id=page_job_id,
                parent_job_id=parent_job_id,
                page_number=page_num,
                page_file_path=str(page_file_path),
                options=options
            )

            # Add page job as child of main job (Redis)
            redis_client.add_child_job(parent_job_id, "page", page_job_id)

        # Mark split job as completed in Redis
        redis_client.set_job_status(
            job_id=split_job_id,
            job_type="split",
            status="completed",
            parent_job_id=parent_job_id,
            completed_at=datetime.utcnow(),
        )

        logger.info(f"[SPLIT JOB {split_job_id}] Completed - {total_pages} page jobs created")

        return {"split_job_id": split_job_id, "pages_created": total_pages}

    except Exception as exc:
        logger.error(f"[SPLIT JOB {split_job_id}] Failed: {exc}", exc_info=True)

        # Update Redis
        redis_client.set_job_status(
            job_id=split_job_id,
            job_type="split",
            status="failed",
            parent_job_id=parent_job_id,
            error=str(exc),
            completed_at=datetime.utcnow(),
        )

        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


# ============================================
# PAGE JOB - Converte página individual
# ============================================

@celery_app.task(bind=True, max_retries=3)
def convert_page_task(
    self,
    page_job_id: str,
    parent_job_id: str,
    page_number: int,
    page_file_path: str,
    options: dict = None,
):
    """
    Page job - converte página individual de PDF

    Args:
        page_job_id: ID deste page job
        parent_job_id: ID do main job
        page_number: Número da página
        page_file_path: Caminho do arquivo da página
        options: Opções de conversão
    """
    if options is None:
        options = {}

    redis_client = get_redis_client()
    es_client = get_es_client()
    converter = get_converter()

    logger.info(f"[PAGE JOB {page_job_id}] Processing page {page_number}")

    # Update MySQL: Set page to processing
    db = SessionLocal()
    try:
        from shared.models import Page as PageModel
        page = db.query(PageModel).filter(
            PageModel.job_id == parent_job_id,
            PageModel.page_number == page_number
        ).first()
        if page:
            page.status = JobStatus.PROCESSING
            db.commit()
    except Exception as e:
        logger.error(f"[PAGE JOB {page_job_id}] MySQL update error: {e}")
    finally:
        db.close()

    try:
        # Mark page job as processing in Redis
        redis_client.set_job_status(
            job_id=page_job_id,
            job_type="page",
            status="processing",
            parent_job_id=parent_job_id,
            page_number=page_number,
            started_at=datetime.utcnow(),
        )

        # Convert page
        page_path = Path(page_file_path)
        result = converter.convert_to_markdown(page_path, options)

        # Store page result in Redis
        redis_client.set_job_result(page_job_id, result)

        # Store page result in Elasticsearch
        markdown_content = result.get("markdown", "")
        metadata = result.get("metadata", {})

        es_success = es_client.store_page_result(
            job_id=parent_job_id,
            page_number=page_number,
            markdown_content=markdown_content,
            metadata=metadata
        )

        # Store page markdown in MinIO
        minio_result_path = None
        try:
            minio_client = get_minio_client()
            minio_object_name = f"results/{parent_job_id}/page_{page_number:04d}.md"
            minio_client.upload_file(
                bucket_name=minio_client.bucket_results,
                object_name=minio_object_name,
                file_data=markdown_content.encode('utf-8'),
                content_type="text/markdown",
            )
            minio_result_path = minio_object_name
            logger.info(f"Page {page_number} markdown uploaded to MinIO: {minio_object_name}")
        except Exception as e:
            logger.error(f"Failed to upload page {page_number} markdown to MinIO: {e}")

        # Update MySQL: Mark page as completed with markdown content
        db = SessionLocal()
        try:
            from shared.models import Page as PageModel
            page = db.query(PageModel).filter(
                PageModel.job_id == parent_job_id,
                PageModel.page_number == page_number
            ).first()
            if page:
                page.status = JobStatus.COMPLETED
                page.markdown_content = markdown_content  # NEW: Store markdown in MySQL
                page.char_count = len(markdown_content)
                page.has_elasticsearch_result = es_success
                page.completed_at = datetime.utcnow()
                db.commit()

            # Update parent job pages_completed count
            parent_job = db.query(Job).filter(Job.id == parent_job_id).first()
            if parent_job:
                completed_count = db.query(PageModel).filter(
                    PageModel.job_id == parent_job_id,
                    PageModel.status == JobStatus.COMPLETED
                ).count()
                parent_job.pages_completed = completed_count
                db.commit()
        except Exception as e:
            logger.error(f"[PAGE JOB {page_job_id}] MySQL completion error: {e}")
        finally:
            db.close()

        # Mark page job as completed in Redis
        redis_client.set_job_status(
            job_id=page_job_id,
            job_type="page",
            status="completed",
            parent_job_id=parent_job_id,
            page_number=page_number,
            completed_at=datetime.utcnow(),
        )

        logger.info(f"[PAGE JOB {page_job_id}] Page {page_number} completed")

        # Update main job progress
        total_pages = redis_client.get_job_pages_total(parent_job_id)
        completed_pages = redis_client.count_completed_page_jobs(parent_job_id)

        if total_pages and completed_pages:
            # Progress: 20% (download) + 70% (pages) + 10% (merge)
            pages_progress = int((completed_pages / total_pages) * 70)
            main_progress = 20 + pages_progress
            redis_client.update_job_progress(parent_job_id, main_progress)

            logger.info(f"[PAGE JOB {page_job_id}] Main job progress: {main_progress}% ({completed_pages}/{total_pages} pages)")

        # Check if all pages completed - trigger merge
        if redis_client.all_page_jobs_completed(parent_job_id):
            logger.info(f"[PAGE JOB {page_job_id}] All pages completed - creating merge job")

            merge_job_id = str(uuid4())
            merge_pages_task.delay(
                merge_job_id=merge_job_id,
                parent_job_id=parent_job_id
            )

            redis_client.add_child_job(parent_job_id, "merge", merge_job_id)

        return {"page_job_id": page_job_id, "page_number": page_number, "status": "completed"}

    except SoftTimeLimitExceeded:
        # Gracefully handle soft timeout - mark as failed and retry
        logger.warning(f"[PAGE JOB {page_job_id}] Page {page_number} soft timeout exceeded - marking as failed for retry")

        error_msg = f"Page conversion exceeded soft time limit ({settings.conversion_timeout_seconds - 30}s)"

        # Update Redis
        redis_client.set_job_status(
            job_id=page_job_id,
            job_type="page",
            status="failed",
            parent_job_id=parent_job_id,
            page_number=page_number,
            error=error_msg,
            completed_at=datetime.utcnow(),
        )

        # Update MySQL
        db = SessionLocal()
        try:
            from shared.models import Page as PageModel
            page = db.query(PageModel).filter(
                PageModel.job_id == parent_job_id,
                PageModel.page_number == page_number
            ).first()
            if page:
                page.status = JobStatus.FAILED
                page.error_message = error_msg
                db.commit()

            # Update parent job pages_failed count
            parent_job = db.query(Job).filter(Job.id == parent_job_id).first()
            if parent_job:
                failed_count = db.query(PageModel).filter(
                    PageModel.job_id == parent_job_id,
                    PageModel.status == JobStatus.FAILED
                ).count()
                parent_job.pages_failed = failed_count
                db.commit()
        except Exception as e:
            logger.error(f"[PAGE JOB {page_job_id}] MySQL update error on timeout: {e}")
        finally:
            db.close()

        # Retry with backoff
        raise self.retry(exc=SoftTimeLimitExceeded(), countdown=30 * (2 ** self.request.retries))

    except Exception as exc:
        logger.error(f"[PAGE JOB {page_job_id}] Page {page_number} failed: {exc}", exc_info=True)

        # Update Redis
        redis_client.set_job_status(
            job_id=page_job_id,
            job_type="page",
            status="failed",
            parent_job_id=parent_job_id,
            page_number=page_number,
            error=str(exc),
            completed_at=datetime.utcnow(),
        )

        # Update MySQL: Mark page as failed
        db = SessionLocal()
        try:
            from shared.models import Page as PageModel
            page = db.query(PageModel).filter(
                PageModel.job_id == parent_job_id,
                PageModel.page_number == page_number
            ).first()
            if page:
                page.status = JobStatus.FAILED
                page.error_message = str(exc)
                db.commit()

            # Update parent job pages_failed count
            parent_job = db.query(Job).filter(Job.id == parent_job_id).first()
            if parent_job:
                failed_count = db.query(PageModel).filter(
                    PageModel.job_id == parent_job_id,
                    PageModel.status == JobStatus.FAILED
                ).count()
                parent_job.pages_failed = failed_count
                db.commit()
        except Exception as e:
            logger.error(f"[PAGE JOB {page_job_id}] MySQL failure error: {e}")
        finally:
            db.close()

        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


# ============================================
# PAGE RETRY - Reprocessa página que falhou
# ============================================

@celery_app.task(bind=True, max_retries=3)
def process_page(
    self,
    job_id: str,
    parent_job_id: str,
    pdf_path: str,
    page_number: int,
    options: dict = None,
):
    """
    Retry task - reprocessa página individual de PDF que falhou

    Args:
        job_id: ID do novo page job (para retry)
        parent_job_id: ID do main job
        pdf_path: Caminho do PDF completo
        page_number: Número da página a processar
        options: Opções de conversão
    """
    if options is None:
        options = {}

    redis_client = get_redis_client()
    es_client = get_es_client()
    converter = get_converter()

    logger.info(f"[RETRY PAGE {job_id}] Retrying page {page_number} of job {parent_job_id}")

    # Update MySQL: Set page to processing
    db = SessionLocal()
    try:
        from shared.models import Page as PageModel
        page = db.query(PageModel).filter(
            PageModel.job_id == parent_job_id,
            PageModel.page_number == page_number
        ).first()
        if page:
            page.status = JobStatus.PROCESSING
            page.page_job_id = job_id  # Update with new job ID
            db.commit()
    except Exception as e:
        logger.error(f"[RETRY PAGE {job_id}] MySQL update error: {e}")
    finally:
        db.close()

    try:
        # Mark page job as processing in Redis
        redis_client.set_job_status(
            job_id=job_id,
            job_type="page",
            status="processing",
            parent_job_id=parent_job_id,
            page_number=page_number,
            started_at=datetime.utcnow(),
        )

        # Extract single page from PDF
        temp_dir = Path(settings.temp_storage_path) / parent_job_id / "retry_pages"
        temp_dir.mkdir(parents=True, exist_ok=True)

        splitter = PDFSplitter(temp_dir)
        page_file = splitter.extract_single_page(Path(pdf_path), page_number)

        logger.info(f"[RETRY PAGE {job_id}] Extracted page {page_number} to {page_file}")

        # Convert page
        result = converter.convert_to_markdown(page_file, options)

        # Store page result in Redis
        redis_client.set_job_result(job_id, result)

        # Store page result in Elasticsearch
        markdown_content = result.get("markdown", "")
        metadata = result.get("metadata", {})

        es_success = es_client.store_page_result(
            job_id=parent_job_id,
            page_number=page_number,
            markdown_content=markdown_content,
            metadata=metadata
        )

        # Store page markdown in MinIO
        minio_result_path = None
        try:
            minio_client = get_minio_client()
            minio_object_name = f"results/{parent_job_id}/page_{page_number:04d}.md"
            minio_client.upload_file(
                bucket_name=minio_client.bucket_results,
                object_name=minio_object_name,
                file_data=markdown_content.encode('utf-8'),
                content_type="text/markdown",
            )
            minio_result_path = minio_object_name
            logger.info(f"[RETRY] Page {page_number} markdown uploaded to MinIO: {minio_object_name}")
        except Exception as e:
            logger.error(f"[RETRY] Failed to upload page {page_number} markdown to MinIO: {e}")

        # Update MySQL: Mark page as completed with markdown content
        db = SessionLocal()
        try:
            from shared.models import Page as PageModel
            page = db.query(PageModel).filter(
                PageModel.job_id == parent_job_id,
                PageModel.page_number == page_number
            ).first()
            if page:
                page.status = JobStatus.COMPLETED
                page.markdown_content = markdown_content  # NEW: Store markdown in MySQL
                page.char_count = len(markdown_content)
                page.has_elasticsearch_result = es_success
                page.completed_at = datetime.utcnow()
                db.commit()

            # Update parent job pages_completed and pages_failed counts
            parent_job = db.query(Job).filter(Job.id == parent_job_id).first()
            if parent_job:
                completed_count = db.query(PageModel).filter(
                    PageModel.job_id == parent_job_id,
                    PageModel.status == JobStatus.COMPLETED
                ).count()
                failed_count = db.query(PageModel).filter(
                    PageModel.job_id == parent_job_id,
                    PageModel.status == JobStatus.FAILED
                ).count()
                parent_job.pages_completed = completed_count
                parent_job.pages_failed = failed_count
                db.commit()
        except Exception as e:
            logger.error(f"[RETRY PAGE {job_id}] MySQL completion error: {e}")
        finally:
            db.close()

        # Mark page job as completed in Redis
        redis_client.set_job_status(
            job_id=job_id,
            job_type="page",
            status="completed",
            parent_job_id=parent_job_id,
            page_number=page_number,
            completed_at=datetime.utcnow(),
        )

        logger.info(f"[RETRY PAGE {job_id}] Page {page_number} retry completed successfully")

        # Update main job progress
        total_pages = redis_client.get_job_pages_total(parent_job_id)
        completed_pages = redis_client.count_completed_page_jobs(parent_job_id)

        if total_pages and completed_pages:
            # Progress: 20% (download) + 70% (pages) + 10% (merge)
            pages_progress = int((completed_pages / total_pages) * 70)
            main_progress = 20 + pages_progress
            redis_client.update_job_progress(parent_job_id, main_progress)

            logger.info(f"[RETRY PAGE {job_id}] Main job progress: {main_progress}% ({completed_pages}/{total_pages} pages)")

        # Check if all pages completed now - trigger merge if needed
        if redis_client.all_page_jobs_completed(parent_job_id):
            logger.info(f"[RETRY PAGE {job_id}] All pages completed - creating merge job")

            merge_job_id = str(uuid4())
            merge_pages_task.delay(
                merge_job_id=merge_job_id,
                parent_job_id=parent_job_id
            )

            redis_client.add_child_job(parent_job_id, "merge", merge_job_id)

        # Cleanup page file
        try:
            if page_file.exists():
                page_file.unlink()
        except Exception:
            pass

        return {"job_id": job_id, "page_number": page_number, "status": "completed"}

    except Exception as exc:
        logger.error(f"[RETRY PAGE {job_id}] Page {page_number} retry failed: {exc}", exc_info=True)

        # Update Redis
        redis_client.set_job_status(
            job_id=job_id,
            job_type="page",
            status="failed",
            parent_job_id=parent_job_id,
            page_number=page_number,
            error=str(exc),
            completed_at=datetime.utcnow(),
        )

        # Update MySQL: Mark page as failed again
        db = SessionLocal()
        try:
            from shared.models import Page as PageModel
            page = db.query(PageModel).filter(
                PageModel.job_id == parent_job_id,
                PageModel.page_number == page_number
            ).first()
            if page:
                page.status = JobStatus.FAILED
                page.error_message = str(exc)
                db.commit()

            # Update parent job pages_failed count
            parent_job = db.query(Job).filter(Job.id == parent_job_id).first()
            if parent_job:
                failed_count = db.query(PageModel).filter(
                    PageModel.job_id == parent_job_id,
                    PageModel.status == JobStatus.FAILED
                ).count()
                parent_job.pages_failed = failed_count
                db.commit()
        except Exception as e:
            logger.error(f"[RETRY PAGE {job_id}] MySQL failure error: {e}")
        finally:
            db.close()

        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


# ============================================
# MERGE JOB - Combina resultados das páginas
# ============================================

@celery_app.task(bind=True, max_retries=2)
def merge_pages_task(
    self,
    merge_job_id: str,
    parent_job_id: str,
):
    """
    Merge job - combina resultados de todas as páginas

    Args:
        merge_job_id: ID deste merge job
        parent_job_id: ID do main job
    """
    redis_client = get_redis_client()
    es_client = get_es_client()

    logger.info(f"[MERGE JOB {merge_job_id}] Starting merge")

    try:
        # Mark merge job as processing in Redis
        redis_client.set_job_status(
            job_id=merge_job_id,
            job_type="merge",
            status="processing",
            parent_job_id=parent_job_id,
            started_at=datetime.utcnow(),
        )

        # Get all page jobs
        page_job_ids = redis_client.get_page_jobs(parent_job_id)
        total_pages = len(page_job_ids)

        logger.info(f"[MERGE JOB {merge_job_id}] Merging {total_pages} pages")

        # Collect all page results in order
        page_results = []
        total_words = 0

        for page_job_id in page_job_ids:
            page_status = redis_client.get_job_status(page_job_id)
            if not page_status:
                continue

            page_num = page_status.get("page_number")
            page_result = redis_client.get_job_result(page_job_id)

            if page_result:
                page_results.append((page_num, page_result["markdown"]))
                total_words += page_result.get("metadata", {}).get("words", 0)

        # Sort by page number
        page_results.sort(key=lambda x: x[0])

        # Combine all pages
        combined_markdown = "\n\n---\n\n".join([markdown for _, markdown in page_results])

        # Create merged result
        merged_result = {
            "markdown": combined_markdown,
            "metadata": {
                "pages": total_pages,
                "words": total_words,
                "format": "pdf",
                "size_bytes": 0,
                "title": None,
                "author": None,
            }
        }

        # Store merged result in main job (Redis)
        redis_client.set_job_result(parent_job_id, merged_result)

        # Store merged result in Elasticsearch
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == parent_job_id).first()
            filename = job.filename if job else None
            user_id = job.user_id if job else None
        finally:
            db.close()

        es_success = es_client.store_job_result(
            job_id=parent_job_id,
            markdown_content=combined_markdown,
            user_id=user_id,
            filename=filename,
            total_pages=total_pages,
            metadata=merged_result.get("metadata", {})
        )

        # Update MySQL: Mark parent job as completed
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == parent_job_id).first()
            if job:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.char_count = len(combined_markdown)
                job.has_elasticsearch_result = es_success
                db.commit()
        except Exception as e:
            logger.error(f"[MERGE JOB {merge_job_id}] MySQL completion error: {e}")
        finally:
            db.close()

        # Mark merge job as completed in Redis
        redis_client.set_job_status(
            job_id=merge_job_id,
            job_type="merge",
            status="completed",
            parent_job_id=parent_job_id,
            completed_at=datetime.utcnow(),
        )

        # Mark main job as completed in Redis
        redis_client.set_job_status(
            job_id=parent_job_id,
            job_type="main",
            status="completed",
            progress=100,
            completed_at=datetime.utcnow(),
        )

        logger.info(f"[MERGE JOB {merge_job_id}] Completed - main job {parent_job_id} finished")

        # Cleanup temp files (pages, merged output and the uploaded file; the original stays in MinIO)
        _remove_job_files(parent_job_id)
        logger.info(f"[MERGE JOB {merge_job_id}] Cleanup completed")

        return {"merge_job_id": merge_job_id, "pages_merged": total_pages}

    except Exception as exc:
        logger.error(f"[MERGE JOB {merge_job_id}] Failed: {exc}", exc_info=True)

        # Update Redis
        redis_client.set_job_status(
            job_id=merge_job_id,
            job_type="merge",
            status="failed",
            parent_job_id=parent_job_id,
            error=str(exc),
            completed_at=datetime.utcnow(),
        )

        # Update MySQL: Mark parent job as failed
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == parent_job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = f"Merge failed: {str(exc)}"
                job.completed_at = datetime.utcnow()
                db.commit()
        except Exception as e:
            logger.error(f"[MERGE JOB {merge_job_id}] MySQL failure error: {e}")
        finally:
            db.close()

        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


# ============================================
# Helper functions
# ============================================

def send_callback(callback_url: str, job_id: str, status: str, result: dict = None):
    """Send webhook callback"""
    import httpx

    payload = {
        "job_id": job_id,
        "status": status,
        "completed_at": datetime.utcnow().isoformat(),
        "result_url": f"/jobs/{job_id}/result",
    }

    if result:
        payload["result"] = result

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(callback_url, json=payload)
            response.raise_for_status()
            logger.info(f"Callback sent successfully to {callback_url}")
    except Exception as e:
        logger.error(f"Failed to send callback: {e}")
        raise


def _store_transcript_outputs(job_id: str, outputs: dict) -> None:
    """Persist transcript formats in the private audio bucket so they outlive the Redis result TTL"""
    try:
        minio_client = get_minio_client()
    except Exception as e:
        logger.warning(f"[MAIN JOB {job_id}] MinIO unavailable, transcript files kept only in Redis: {e}")
        return

    for fmt, content in outputs.items():
        # Empty outputs are valid (e.g. SRT of a recording without speech) and stored too
        try:
            minio_client.upload_file(
                bucket_name=minio_client.bucket_audio,
                object_name=transcript_object_name(job_id, fmt),
                file_data=content.encode('utf-8'),
                content_type=TRANSCRIPT_CONTENT_TYPES[fmt],
            )
        except Exception as e:
            logger.warning(f"[MAIN JOB {job_id}] Failed to store transcript.{fmt} in MinIO: {e}")
