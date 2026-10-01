from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Body, Depends, Request, Query
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from typing import Optional, List, Tuple
from pathlib import Path
import hashlib
import os
import shutil
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import logging

from shared.schemas import (
    ConvertRequest,
    JobCreatedResponse,
    JobStatusResponse,
    JobResultResponse,
    JobPagesResponse,
    PageStatus,
    PageJobInfo,
    HealthCheckResponse,
    ConversionOptions,
    JobType,
    JobStatus,
    ChildJobs,
)
from shared.redis_client import get_redis_client
from shared.elasticsearch_client import get_es_client
from shared.minio_client import get_minio_client
from shared.transcripts import TRANSCRIPT_CONTENT_TYPES, TRANSCRIPT_FORMATS, transcript_object_name
from shared.database import SessionLocal, get_db
from shared.models import Job, JobTag, Page, JobStatus as DBJobStatus, User
from shared.config import get_settings
from shared.utils import calculate_file_checksum
from shared.auth import get_current_active_user
from api.deps import get_owned_job, get_owned_page_or_none
from shared.utils import sanitize_upload_filename
from shared.tags import set_job_tags
from api.tag_routes import TAGS_FORM_DESCRIPTION, add_tags_to_existing_job, parse_tags_or_422
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Conversion"])
settings = get_settings()

# Validade da URL pré-assinada do PDF de uma página.
#
# 15 minutos é o meio-termo entre dois erros: um TTL curto demais faz o PDF
# falhar no meio do carregamento (arquivos grandes, conexão ruim, o pdf.js
# refazendo requisições de range) e obriga o usuário a recarregar; um TTL longo
# transforma a URL — que trafega em JSON, fica no histórico do navegador, em
# logs de proxy e no Referer — num link público de longa duração, que é
# exatamente o problema que estamos fechando. 15 min cobre com folga o
# carregamento e a leitura de uma página, e o front pede outra URL ao trocar de
# página, então a renovação é transparente.
PAGE_PDF_URL_TTL_SECONDS = 15 * 60


@router.post("/upload", response_model=JobCreatedResponse, summary="Upload e converter arquivo")
async def upload_and_convert(
    file: UploadFile = File(..., description="Arquivo para conversão (PDF, DOCX, HTML, etc.)"),
    name: Optional[str] = Form(None, description="Nome de identificação (opcional, padrão: nome do arquivo)"),
    tags: Optional[str] = Form(None, description=TAGS_FORM_DESCRIPTION),
    docling_preset: Optional[str] = Form(
        "fast",
        description="Quality/speed preset for PDF conversion: 'fast' (~35s/MB, text-only), 'balanced' (~70-105s/MB, with images), 'quality' (~350s/MB, with OCR)"
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Upload direto de arquivo para conversão

    Este endpoint é dedicado exclusivamente para upload de arquivos.
    Use os outros endpoints para converter de URL, Google Drive ou Dropbox.

    ## Parâmetros:
    - `file`: Arquivo para upload
    - `name`: Nome de identificação opcional (se não fornecido, usa o nome do arquivo)
    - `docling_preset`: Quality/speed preset (apenas para PDFs):
      - **fast** (padrão): Conversão rápida, apenas texto (~35s/MB)
        - OCR: Desligado | Images: Desligadas | Tables: Ligadas
      - **balanced**: Velocidade moderada, extrai imagens (~70-105s/MB)
        - OCR: Desligado | Images: Ligadas | Tables: Ligadas
      - **quality**: Máxima qualidade, inclui OCR para documentos escaneados (~350s/MB)
        - OCR: Ligado | Images: Ligadas | Tables: Ligadas

    ## Formatos suportados
    PDF, DOCX, DOC, HTML, PPTX, XLSX, RTF, ODT

    ## Retorno
    Retorna imediatamente um `job_id` para consultar o progresso via `/jobs/{job_id}`

    ## Exemplos:
    ```bash
    # Fast mode (default)
    curl -X POST http://localhost:8000/upload \
      -H "X-API-Key: your-api-key" \
      -F "file=@documento.pdf"

    # Quality mode with OCR
    curl -X POST http://localhost:8000/upload \
      -H "X-API-Key: your-api-key" \
      -F "file=@documento_escaneado.pdf" \
      -F "docling_preset=quality"
    ```
    """
    tag_list = parse_tags_or_422(tags)
    redis_client = get_redis_client()

    filename = sanitize_upload_filename(file.filename)

    # Stream the upload to disk in chunks (size limit + checksum) instead of reading it into memory
    staging_path = _upload_staging_path(filename)
    try:
        file_size_bytes, file_checksum = await _stream_upload_to_file(file, staging_path, settings.max_file_size_mb)
        file_size_mb = file_size_bytes / (1024 * 1024)

        logger.info(f"File uploaded: {filename} ({file_size_mb:.2f}MB)")
        logger.info(f"File checksum: {file_checksum}")

        # Check if file already processed by this user
        existing_job = db.query(Job).filter(
            Job.user_id == current_user.id,
            Job.file_checksum == file_checksum,
            Job.job_type == "MAIN",
            # A failed job must not swallow a resubmission: sending the file again is the retry
            Job.status != DBJobStatus.FAILED,
        ).first()

        if existing_job:
            logger.info(f"Duplicate file detected! Returning existing job: {existing_job.id}")
            add_tags_to_existing_job(db, existing_job, tag_list)
            return JobCreatedResponse(
                job_id=existing_job.id,
                status="queued",  # Use current status from DB
                created_at=existing_job.created_at,
                message=f"Arquivo já foi processado anteriormente (job existente: {existing_job.id})"
            )

        # Generate job ID for new file
        job_id = uuid4()
        created_at = datetime.utcnow()

        # Determine job name (use provided name or filename)
        job_name = name if name else filename

        # Detect MIME type
        mime_type = file.content_type or "application/octet-stream"

        # Store initial job status in Redis
        redis_client.set_job_status(
            job_id=str(job_id),
            job_type="main",
            status="queued",
            progress=0,
            name=job_name,
        )

        # Set job ownership
        redis_client.set_job_owner(str(job_id), current_user.id)
        redis_client.add_job_to_user(current_user.id, str(job_id))

        # Create Job record in MySQL
        try:
            db_job = Job(
                id=str(job_id),
                user_id=current_user.id,
                filename=filename,
                name=job_name,  # Save user-friendly name
                source_type="file",
                file_size_bytes=file_size_bytes,
                mime_type=mime_type,
                file_checksum=file_checksum,  # Save checksum for deduplication
                status=DBJobStatus.PENDING,
                job_type="MAIN",
                created_at=created_at,
            )
            db.add(db_job)
            set_job_tags(db_job, tag_list)
            db.commit()
            logger.info(f"Job {job_id} created in MySQL with name: {job_name} and checksum: {file_checksum}")
        except Exception as e:
            logger.error(f"Error creating job in MySQL: {e}", exc_info=True)
            db.rollback()
            # Continue - MySQL is for persistence, Redis is primary

        logger.info(f"MAIN JOB created: {job_id} | user: {current_user.username} | source_type: file")

        # Save file to MinIO and temporarily to filesystem
        try:
            from workers.tasks import process_conversion

            # Move the streamed upload to the job's directory (read by the worker)
            temp_file_path = _move_upload_to_job_dir(staging_path, job_id, filename)
            logger.info(f"File saved to filesystem: {temp_file_path}")

            # Save to MinIO (streamed from disk)
            minio_client = get_minio_client()
            minio_object_name = f"uploads/{job_id}/{filename}"
            try:
                minio_client.upload_file(
                    bucket_name=minio_client.bucket_uploads,
                    object_name=minio_object_name,
                    file_path=str(temp_file_path),
                    content_type=file.content_type or "application/octet-stream",
                )
                logger.info(f"File uploaded to MinIO: {minio_object_name}")

                # Update MySQL job with MinIO path
                try:
                    db_job.minio_upload_path = minio_object_name
                    db.commit()
                except Exception as e:
                    logger.warning(f"Failed to update job MinIO path in MySQL: {e}")
                    db.rollback()
            except Exception as e:
                logger.error(f"Failed to upload file to MinIO: {e}")
                # Continue with filesystem fallback

            # Enqueue task
            process_conversion.delay(
                job_id=str(job_id),
                source_type="file",
                source=str(temp_file_path),
                options={"docling_preset": docling_preset},
            )
            logger.info(f"MAIN JOB {job_id} enqueued to Celery successfully")

        except ImportError as e:
            logger.error(f"Celery tasks not available: {e}")
            redis_client.set_job_status(
                job_id=str(job_id),
                job_type="main",
                status="failed",
                progress=0,
                error="Celery workers não disponíveis"
            )
            # Update MySQL
            try:
                db_job.status = DBJobStatus.FAILED
                db_job.error_message = "Celery workers não disponíveis"
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(status_code=503, detail="Sistema de processamento indisponível")
        except Exception as e:
            logger.error(f"Error enqueueing job {job_id}: {e}", exc_info=True)
            redis_client.set_job_status(
                job_id=str(job_id),
                job_type="main",
                status="failed",
                progress=0,
                error=str(e)
            )
            # Update MySQL
            try:
                db_job.status = DBJobStatus.FAILED
                db_job.error_message = str(e)
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(status_code=500, detail="Erro ao criar job")

        return JobCreatedResponse(
            job_id=job_id,
            status="queued",
            created_at=created_at,
            message="Job enfileirado para processamento"
        )
    finally:
        # Remove the staged upload unless it was moved to the job directory
        staging_path.unlink(missing_ok=True)


TRANSCRIPT_OUTPUT_FORMATS = ["markdown", "vtt", "srt", "txt", "json"]

AUDIO_MIME_TYPES = [
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/wave", "audio/x-wav",
    "audio/m4a", "audio/x-m4a", "audio/mp4", "audio/flac", "audio/ogg",
    "audio/opus", "audio/webm", "audio/wma", "audio/x-ms-wma", "audio/aac", "audio/x-aac",
]
AUDIO_EXTENSIONS = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus', '.webm', '.wma', '.aac', '.oga', '.spx']

VIDEO_MIME_TYPES = [
    "video/mp4", "video/x-m4v", "video/x-matroska", "video/quicktime", "video/x-msvideo",
    "video/webm", "video/x-ms-wmv", "video/x-flv", "video/mpeg", "video/mp2t", "video/3gpp",
]
VIDEO_EXTENSIONS = ['.mp4', '.m4v', '.mkv', '.mov', '.avi', '.webm', '.wmv', '.flv', '.mpeg', '.mpg', '.ts', '.3gp']


UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB


STAGING_MAX_SUFFIX_BYTES = 16


def _upload_staging_path(filename: str, area: str = "uploads") -> Path:
    """
    Temporary location for an upload before its job exists (unique per request).

    Only a short extension is kept (the name is a UUID), so the staging name stays
    far below the 255-byte filename limit even for long sanitized names.
    """
    suffix = Path(filename).suffix
    if len(suffix.encode("utf-8")) > STAGING_MAX_SUFFIX_BYTES:
        suffix = ""
    return Path(settings.temp_storage_path) / area / ".staging" / f"{uuid4()}{suffix}"


def _move_upload_to_job_dir(staging_path: Path, job_id, filename: str) -> Path:
    """Move a streamed upload to {temp}/uploads/{job_id}/, where the worker reads it"""
    temp_dir = Path(settings.temp_storage_path) / "uploads" / str(job_id)
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / filename
    os.replace(staging_path, temp_file_path)
    return temp_file_path


async def _stream_upload_to_file(file: UploadFile, destination: Path, max_size_mb: int) -> Tuple[int, str]:
    """
    Copy an upload to disk in chunks, enforcing the size limit and computing its SHA256.

    Returns:
        (size in bytes, sha256 hex digest)
    """
    max_bytes = max_size_mb * 1024 * 1024
    hasher = hashlib.sha256()
    size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(destination, "wb") as out:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Arquivo muito grande. Máximo: {max_size_mb}MB"
                    )
                hasher.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Arquivo enviado está vazio")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return size, hasher.hexdigest()


@router.post("/transcribe", response_model=JobCreatedResponse, summary="Transcrever áudio ou vídeo (STT, legendas VTT/SRT)")
async def transcribe_audio(
    file: UploadFile = File(..., description="Arquivo de áudio (MP3, WAV, M4A, FLAC, OGG...) ou vídeo (MP4, MKV, MOV, WEBM, AVI...)"),
    name: Optional[str] = Form(None, description="Nome de identificação (opcional, padrão: nome do arquivo)"),
    tags: Optional[str] = Form(None, description=TAGS_FORM_DESCRIPTION),
    language: Optional[str] = Form(None, description="Código do idioma (ex: 'en', 'pt'). Auto-detectar se não fornecido"),
    include_timestamps: bool = Form(True, description="Incluir marcadores de tempo na transcrição"),
    include_word_timestamps: bool = Form(False, description="Incluir timestamps em nível de palavra (mais detalhado)"),
    output_format: str = Form(
        "markdown",
        description="Formato padrão do resultado em /jobs/{job_id}/result: markdown, vtt, srt, txt ou json",
    ),
    purge_source: bool = Form(
        False,
        description="Apagar o áudio/vídeo enviado assim que a transcrição terminar (guarda só o texto)",
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Transcrever áudio ou vídeo para texto usando Whisper (STT)

    Aceita áudio ou vídeo (só a faixa de áudio do vídeo é transcrita).
    O job entra na fila própria de transcrição (`ingestify-audio`), consumida por
    workers dedicados, e não disputa vaga com a conversão de documentos.

    ## Autenticação
    Obrigatória: header `X-API-Key: <chave>` ou `Authorization: Bearer <token JWT>`.
    Sem ele a resposta é 401.

    Todos os formatos são gerados: Markdown, legendas WebVTT e SRT, texto puro e
    JSON com segmentos. Escolha o formato em `GET /jobs/{job_id}/result?format=vtt`
    (ou defina o padrão com `output_format`).

    ## Parâmetros:
    - `file`: Arquivo de áudio ou vídeo para transcrição
    - `name`: Nome de identificação opcional
    - `tags`: Tags do job, separadas por vírgula (ex: `focus,aula`)
    - `language`: Código de idioma ISO 639-1 (ex: 'en', 'pt', 'es'). Auto-detecta se não fornecido
    - `include_timestamps`: Adicionar marcadores de tempo [MM:SS] na transcrição
    - `include_word_timestamps`: Adicionar timestamps em cada palavra (mais detalhado)
    - `output_format`: Formato padrão do resultado (`markdown`, `vtt`, `srt`, `txt`, `json`)
    - `purge_source`: Se `true`, apaga o arquivo enviado (disco e MinIO) quando o job
      termina com sucesso; ficam só as transcrições. `DELETE /jobs/{job_id}` também
      apaga o arquivo de origem e as transcrições

    ## Arquivo repetido
    Reenviar um arquivo idêntico (mesmo SHA-256) que já tem job **não falho** devolve
    esse job em vez de criar outro: as tags novas são somadas às dele e o
    `output_format` enviado passa a ser o padrão do resultado. Se o job anterior
    falhou, o reenvio cria um job novo; é assim que se tenta de novo.

    ## Formatos suportados
    - Áudio: MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC
    - Vídeo: MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP

    ## Limite de tamanho
    - Áudio: até 50MB (MAX_AUDIO_FILE_SIZE_MB)
    - Vídeo: até 500MB (MAX_VIDEO_FILE_SIZE_MB)

    ## Tempo limite
    Definido pelo worker de transcrição (`TRANSCRIPTION_TIMEOUT_SECONDS`, padrão 3h),
    independente do `CONVERSION_TIMEOUT_SECONDS` dos documentos. Um job que estoura o
    tempo falha sem novas tentativas automáticas.

    ## Retorno
    Retorna imediatamente um `job_id` para consultar o progresso via `/jobs/{job_id}`

    ## Erros
    - 401: sem autenticação
    - 413: arquivo acima do limite
    - 422: formato não suportado, `output_format` inválido ou `tags` inválidas
    - 503: transcrição desabilitada ou workers indisponíveis

    ## Exemplos:
    ```bash
    curl -X POST http://localhost:8080/transcribe \\
      -H "X-API-Key: $INGESTIFY_API_KEY" \\
      -F "file=@meeting.mp3" \\
      -F "language=pt" \\
      -F "include_timestamps=true"
    ```

    Vídeo com legenda SRT como padrão, tags e descarte do arquivo ao terminar:
    ```bash
    curl -X POST http://localhost:8080/transcribe \\
      -H "Authorization: Bearer $TOKEN" \\
      -F "file=@aula.mp4" \\
      -F "language=pt" \\
      -F "output_format=srt" \\
      -F "tags=focus,aula" \\
      -F "purge_source=true"
    ```

    ## Resultado
    Consulte o status em `/jobs/{job_id}` até `completed` e busque o resultado:
    - `GET /jobs/{job_id}/result`: JSON com markdown e metadados (idioma, duração, device)
    - `GET /jobs/{job_id}/result?format=vtt`: legenda WebVTT (`text/vtt`)
    - `?format=srt`, `?format=txt`, `?format=json`: SRT, texto puro, segmentos
    """
    # Check if audio transcription is enabled
    if not settings.enable_audio_transcription:
        raise HTTPException(
            status_code=503,
            detail="Audio transcription is currently disabled"
        )

    tag_list = parse_tags_or_422(tags)
    redis_client = get_redis_client()

    filename = sanitize_upload_filename(file.filename)

    output_format = (output_format or "markdown").lower()
    if output_format not in TRANSCRIPT_OUTPUT_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=f"output_format inválido: {output_format}. Use: {', '.join(TRANSCRIPT_OUTPUT_FORMATS)}"
        )

    # Validate media type (audio or video), by MIME type or extension
    mime_type = file.content_type or "application/octet-stream"
    file_ext = filename.lower()[filename.rfind('.'):] if '.' in filename else ''

    is_video = mime_type in VIDEO_MIME_TYPES or (
        file_ext in VIDEO_EXTENSIONS and mime_type not in AUDIO_MIME_TYPES
    )
    is_audio = mime_type in AUDIO_MIME_TYPES or file_ext in AUDIO_EXTENSIONS

    if not is_video and not is_audio:
        raise HTTPException(
            status_code=422,
            detail=f"Formato não suportado. MIME type: {mime_type}, Extensão: {file_ext}. "
                   f"Áudio: MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC. "
                   f"Vídeo: MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP"
        )

    media_kind = "video" if is_video else "audio"
    max_size_mb = settings.max_video_file_size_mb if is_video else settings.max_audio_file_size_mb

    # Stream the upload to disk in chunks (size limit + checksum) instead of
    # holding up to max_size_mb in memory
    staging_path = _upload_staging_path(filename, "audio")
    try:
        file_size_bytes, file_checksum = await _stream_upload_to_file(file, staging_path, max_size_mb)
        file_size_mb = file_size_bytes / (1024 * 1024)

        logger.info(f"{media_kind.capitalize()} file uploaded: {filename} ({file_size_mb:.2f}MB, {mime_type})")
        logger.info(f"Audio file checksum: {file_checksum}")

        # Check if file already processed by this user
        existing_job = db.query(Job).filter(
            Job.user_id == current_user.id,
            Job.file_checksum == file_checksum,
            Job.job_type == "MAIN",
            # A failed job must not swallow a resubmission: sending the file again is the retry
            Job.status != DBJobStatus.FAILED,
        ).first()

        if existing_job:
            logger.info(f"Duplicate audio file detected! Returning existing job: {existing_job.id}")
            add_tags_to_existing_job(db, existing_job, tag_list)
            # The latest request decides the default result format of the reused job
            redis_client.set_job_output_format(str(existing_job.id), output_format)
            return JobCreatedResponse(
                job_id=existing_job.id,
                status="queued",
                created_at=existing_job.created_at,
                message=f"Arquivo de áudio já foi processado anteriormente (job existente: {existing_job.id})"
            )

        # Generate job ID for new file
        job_id = uuid4()
        created_at = datetime.utcnow()

        # Determine job name
        job_name = name if name else filename

        # Store initial job status in Redis
        redis_client.set_job_status(
            job_id=str(job_id),
            job_type="main",
            status="queued",
            progress=0,
            name=job_name,
        )

        # Set job ownership
        redis_client.set_job_owner(str(job_id), current_user.id)
        redis_client.add_job_to_user(current_user.id, str(job_id))
        redis_client.set_job_output_format(str(job_id), output_format)

        # Create Job record in MySQL
        try:
            db_job = Job(
                id=str(job_id),
                user_id=current_user.id,
                filename=filename,
                name=job_name,  # Save user-friendly name
                source_type="audio",
                file_size_bytes=file_size_bytes,
                mime_type=mime_type,
                file_checksum=file_checksum,  # Save checksum for deduplication
                status=DBJobStatus.PENDING,
                job_type="MAIN",
                created_at=created_at,
            )
            db.add(db_job)
            set_job_tags(db_job, tag_list)
            db.commit()
            logger.info(f"Audio transcription job {job_id} created in MySQL with name: {job_name} and checksum: {file_checksum}")
        except Exception as e:
            logger.error(f"Error creating audio job in MySQL: {e}", exc_info=True)
            db.rollback()

        logger.info(f"AUDIO TRANSCRIPTION JOB created: {job_id} | user: {current_user.username}")

        # Save audio file to MinIO and temporarily to filesystem
        try:
            from workers.tasks import process_conversion

            # Move the streamed upload to the job's directory (read by the worker)
            temp_dir = Path(settings.temp_storage_path) / "audio" / str(job_id)
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / filename
            os.replace(staging_path, temp_file_path)
            logger.info(f"Audio file saved to filesystem: {temp_file_path}")

            # Save to MinIO (streamed from disk)
            minio_client = get_minio_client()
            minio_object_name = f"audio/{job_id}/{filename}"
            try:
                minio_client.upload_file(
                    bucket_name=minio_client.bucket_audio,
                    object_name=minio_object_name,
                    file_path=str(temp_file_path),
                    content_type=file.content_type or "audio/mpeg",
                )
                logger.info(f"Audio file uploaded to MinIO: {minio_object_name}")

                # Update MySQL job with MinIO path
                try:
                    db_job.minio_upload_path = minio_object_name
                    db.commit()
                except Exception as e:
                    logger.warning(f"Failed to update audio job MinIO path in MySQL: {e}")
                    db.rollback()
            except Exception as e:
                logger.error(f"Failed to upload audio file to MinIO: {e}")
                # Continue with filesystem fallback

            # Build audio transcription options
            options = {
                "language": language,
                "include_timestamps": include_timestamps,
                "include_word_timestamps": include_word_timestamps,
                "output_format": output_format,
                "media_kind": media_kind,
                "is_audio": True,  # Flag to indicate this is audio transcription
                "purge_source": purge_source,
            }

            # Enqueue task (use 'file' source type since audio is already saved locally)
            # on the transcription queue, served by the dedicated worker-audio service
            process_conversion.apply_async(
                kwargs=dict(
                    job_id=str(job_id),
                    source_type="file",
                    source=str(temp_file_path),
                    options=options,
                ),
                queue=settings.transcription_queue,
            )
            logger.info(f"AUDIO JOB {job_id} enqueued to Celery successfully")

        except ImportError as e:
            logger.error(f"Celery tasks not available: {e}")
            redis_client.set_job_status(
                job_id=str(job_id),
                job_type="main",
                status="failed",
                progress=0,
                error="Celery workers não disponíveis"
            )
            # Update MySQL
            try:
                db_job.status = DBJobStatus.FAILED
                db_job.error_message = "Celery workers não disponíveis"
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(status_code=503, detail="Sistema de processamento indisponível")
        except Exception as e:
            logger.error(f"Error enqueueing audio job {job_id}: {e}", exc_info=True)
            redis_client.set_job_status(
                job_id=str(job_id),
                job_type="main",
                status="failed",
                progress=0,
                error=str(e)
            )
            # Update MySQL
            try:
                db_job.status = DBJobStatus.FAILED
                db_job.error_message = str(e)
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(status_code=500, detail="Erro ao criar job de transcrição")

        return JobCreatedResponse(
            job_id=job_id,
            status="queued",
            created_at=created_at,
            message="Job de transcrição de áudio enfileirado para processamento"
        )
    finally:
        # Remove the staged upload unless it was moved to the job directory
        staging_path.unlink(missing_ok=True)


@router.post("/convert", response_model=JobCreatedResponse)
async def convert_document(
    source_type: str = Form(
        ...,
        description="Tipo de fonte: 'file' (upload), 'url' (URL pública), 'gdrive' (Google Drive), 'dropbox' (Dropbox)",
        example="file"
    ),
    source: Optional[str] = Form(
        None,
        description="URL, file_id (Google Drive) ou path (Dropbox). Deixe vazio para upload de arquivo",
        example="https://example.com/document.pdf"
    ),
    file: Optional[UploadFile] = File(
        None,
        description="Arquivo para upload direto (use quando source_type='file')"
    ),
    name: Optional[str] = Form(
        None,
        description="Nome de identificação opcional (padrão: nome do arquivo ou URL)"
    ),
    tags: Optional[str] = Form(None, description=TAGS_FORM_DESCRIPTION),
    authorization: Optional[str] = Header(
        None,
        description="Token de autenticação no formato 'Bearer {token}' (obrigatório para gdrive e dropbox)"
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Conversão de documentos para Markdown

    ## Opções de uso:

    ### 1. Upload de arquivo (multipart/form-data)
    - `source_type`: "file"
    - `file`: Selecione o arquivo para upload
    - `source`: Deixe vazio

    ### 2. URL pública
    - `source_type`: "url"
    - `source`: "https://example.com/document.pdf"
    - `file`: Deixe vazio

    ### 3. Google Drive
    - `source_type`: "gdrive"
    - `source`: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" (file ID)
    - `authorization`: "Bearer ya29.a0AfH6SMB..." (OAuth2 token)
    - `file`: Deixe vazio

    ### 4. Dropbox
    - `source_type`: "dropbox"
    - `source`: "/documents/report.pdf" (path do arquivo)
    - `authorization`: "Bearer sl.B1a2c3..." (access token)
    - `file`: Deixe vazio

    ## Formatos suportados
    PDF, DOCX, DOC, HTML, PPTX, XLSX, RTF, ODT

    ## Retorno
    Retorna imediatamente um `job_id` para consultar o progresso via `/jobs/{job_id}`
    """
    redis_client = get_redis_client()

    # Validate source_type
    if source_type not in ["file", "url", "gdrive", "dropbox"]:
        raise HTTPException(
            status_code=400,
            detail=f"source_type inválido: {source_type}. Use: file, url, gdrive ou dropbox"
        )

    # Validate file upload
    if source_type == "file" and not file:
        raise HTTPException(status_code=400, detail="Arquivo é obrigatório para source_type=file")

    # For uploads the worker reads the file saved by the API. Never forward a
    # client-supplied `source`, otherwise it is used as a path on the worker.
    if source_type == "file":
        source = None

    # Validate source for non-file types
    if source_type != "file" and not source:
        raise HTTPException(status_code=400, detail=f"source é obrigatório para source_type={source_type}")

    tag_list = parse_tags_or_422(tags)

    # Validate authentication for gdrive and dropbox
    if source_type in ["gdrive", "dropbox"] and not authorization:
        raise HTTPException(status_code=401, detail="Authorization header é obrigatório para esta fonte")

    # Stream the uploaded file (if any) to disk in chunks (size limit + checksum)
    staging_path = None
    try:
        filename = None
        file_size_bytes = 0
        mime_type = None
        file_checksum = None

        if file:
            filename = sanitize_upload_filename(file.filename)
            mime_type = file.content_type or "application/octet-stream"

            # Rejects empty uploads (400) and files over the limit (413)
            staging_path = _upload_staging_path(filename)
            file_size_bytes, file_checksum = await _stream_upload_to_file(file, staging_path, settings.max_file_size_mb)
            file_size_mb = file_size_bytes / (1024 * 1024)

            logger.info(f"File uploaded: {filename} ({file_size_mb:.2f}MB)")
            logger.info(f"File checksum: {file_checksum}")

            # Check if file already processed by this user
            existing_job = db.query(Job).filter(
                Job.user_id == current_user.id,
                Job.file_checksum == file_checksum,
                Job.job_type == "MAIN"
            ).first()

            if existing_job:
                logger.info(f"Duplicate file detected! Returning existing job: {existing_job.id}")
                add_tags_to_existing_job(db, existing_job, tag_list)
                return JobCreatedResponse(
                    job_id=existing_job.id,
                    status="queued",
                    created_at=existing_job.created_at,
                    message=f"Arquivo já foi processado anteriormente (job existente: {existing_job.id})"
                )

        # Generate job ID for new conversion
        job_id = uuid4()
        created_at = datetime.utcnow()

        # Determine job name (use provided name or auto-detect)
        if name:
            job_name = name
        elif filename:
            job_name = filename
        elif source:
            # Extract name from URL or path
            if source_type == "url":
                job_name = source.split('/')[-1] or source
            else:
                job_name = source.split('/')[-1] or source
        else:
            job_name = f"Job {job_id}"

        # Store initial job status in Redis
        redis_client.set_job_status(
            job_id=str(job_id),
            job_type="main",
            status="queued",
            progress=0,
            name=job_name,
        )

        # Set job ownership
        redis_client.set_job_owner(str(job_id), current_user.id)
        redis_client.add_job_to_user(current_user.id, str(job_id))

        # Create Job record in MySQL
        try:
            db_job = Job(
                id=str(job_id),
                user_id=current_user.id,
                filename=filename or job_name,
                name=job_name,  # Save user-friendly name
                source_type=source_type,
                source_url=source if source_type != "file" else None,
                file_size_bytes=file_size_bytes if file_size_bytes > 0 else None,
                mime_type=mime_type,
                file_checksum=file_checksum,  # Save checksum for deduplication (only for file uploads)
                status=DBJobStatus.PENDING,
                job_type="MAIN",
                created_at=created_at,
            )
            db.add(db_job)
            set_job_tags(db_job, tag_list)
            db.commit()
            checksum_info = f" and checksum: {file_checksum}" if file_checksum else ""
            logger.info(f"Job {job_id} created in MySQL with name: {job_name} (source_type: {source_type}){checksum_info}")
        except Exception as e:
            logger.error(f"Error creating job in MySQL: {e}", exc_info=True)
            db.rollback()
            # Continue - MySQL is for persistence, Redis is primary

        logger.info(f"MAIN JOB created: {job_id} | user: {current_user.username} | source_type: {source_type}")

        # Enqueue Celery task
        try:
            from workers.tasks import process_conversion
            import os
            from pathlib import Path

            # Prepare task arguments
            task_kwargs = {
                "job_id": str(job_id),
                "source_type": source_type,
                "source": source,
                "options": {},  # Default options for now
            }

            # Add auth token if present
            if authorization and authorization.startswith("Bearer "):
                task_kwargs["auth_token"] = authorization.replace("Bearer ", "")

            # Save file to MinIO and temporarily to filesystem if uploaded
            if staging_path:
                # Move the streamed upload to the job's directory (read by the worker)
                temp_file_path = _move_upload_to_job_dir(staging_path, job_id, filename)
                task_kwargs["source"] = str(temp_file_path)
                logger.info(f"File saved to filesystem: {temp_file_path}")

                # Save to MinIO (streamed from disk)
                minio_client = get_minio_client()
                minio_object_name = f"uploads/{job_id}/{filename}"
                try:
                    minio_client.upload_file(
                        bucket_name=minio_client.bucket_uploads,
                        object_name=minio_object_name,
                        file_path=str(temp_file_path),
                        content_type=mime_type or "application/octet-stream",
                    )
                    logger.info(f"File uploaded to MinIO: {minio_object_name}")

                    # Update MySQL job with MinIO path
                    try:
                        db_job.minio_upload_path = minio_object_name
                        db.commit()
                    except Exception as e:
                        logger.warning(f"Failed to update job MinIO path in MySQL: {e}")
                        db.rollback()
                except Exception as e:
                    logger.error(f"Failed to upload file to MinIO: {e}")
                    # Continue with filesystem fallback

            # Enqueue task
            process_conversion.delay(**task_kwargs)
            logger.info(f"MAIN JOB {job_id} enqueued to Celery successfully")

        except ImportError as e:
            logger.error(f"Celery tasks not available: {e}")
            redis_client.set_job_status(
                job_id=str(job_id),
                job_type="main",
                status="failed",
                progress=0,
                error="Celery workers não disponíveis"
            )
            # Update MySQL
            try:
                db_job.status = DBJobStatus.FAILED
                db_job.error_message = "Celery workers não disponíveis"
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(status_code=503, detail="Sistema de processamento indisponível")
        except Exception as e:
            logger.error(f"Error enqueueing job {job_id}: {e}", exc_info=True)
            redis_client.set_job_status(
                job_id=str(job_id),
                job_type="main",
                status="failed",
                progress=0,
                error=str(e)
            )
            # Update MySQL
            try:
                db_job.status = DBJobStatus.FAILED
                db_job.error_message = str(e)
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(status_code=500, detail="Erro ao criar job")

        return JobCreatedResponse(
            job_id=job_id,
            status="queued",
            created_at=created_at,
            message="Job enfileirado para processamento"
        )
    finally:
        # Remove the staged upload unless it was moved to the job directory
        if staging_path:
            staging_path.unlink(missing_ok=True)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    owned_job: Optional[Job] = Depends(get_owned_job),
    db: Session = Depends(get_db),
    page_limit: Optional[int] = None,
    page_offset: int = 0,
):
    """
    Consultar status de qualquer tipo de job (main, split, page, merge)

    ## Pagination for pages list:
    - `page_limit`: Maximum number of pages to return (default: all pages)
    - `page_offset`: Number of pages to skip (default: 0)

    Example: GET /jobs/{job_id}?page_limit=50&page_offset=0

    ## Permissões:
    - Apenas o dono do job (verificado no MySQL) pode consultá-lo.
      Jobs de outros usuários retornam 404.
    """
    redis_client = get_redis_client()

    # Ownership já validada em get_owned_job (MySQL como fonte da verdade)

    # Get job status from Redis (real-time data)
    status_data = redis_client.get_job_status(job_id)

    if not status_data:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado")

    # Get job metadata from MySQL (child jobs não possuem linha própria)
    db_job = owned_job if (owned_job is not None and owned_job.id == job_id) else None

    # Parse timestamps
    started_at = None
    completed_at = None
    created_at = datetime.utcnow()  # Default

    if db_job:
        created_at = db_job.created_at
        started_at = db_job.started_at
        completed_at = db_job.completed_at
    else:
        # Fallback to Redis timestamps
        if "started_at" in status_data and status_data["started_at"]:
            started_at = datetime.fromisoformat(status_data["started_at"])
        if "completed_at" in status_data and status_data["completed_at"]:
            completed_at = datetime.fromisoformat(status_data["completed_at"])

    # Get job type (convert to lowercase for schema validation)
    job_type = status_data.get("type", "main").lower()

    # Build response based on job type
    response_data = {
        "job_id": job_id,
        "type": job_type,
        "status": status_data.get("status", "unknown"),
        "progress": status_data.get("progress", 0),
        "created_at": created_at,
        "started_at": started_at,
        "completed_at": completed_at,
        "error": status_data.get("error"),
        # Workers rewrite the Redis status without the name, so MySQL (where
        # /upload, /convert and /transcribe store it) is the fallback.
        "name": status_data.get("name") or (
            owned_job.name if owned_job is not None and str(owned_job.id) == job_id else None
        ),
        "tags": owned_job.tags if owned_job is not None and str(owned_job.id) == job_id else [],
    }

    # Add parent_job_id for child jobs (split, page, merge)
    if "parent_job_id" in status_data:
        response_data["parent_job_id"] = status_data["parent_job_id"]

    # Add page_number for page jobs
    if "page_number" in status_data:
        response_data["page_number"] = status_data["page_number"]

    # Transcription progress in media time (set by the audio worker as it goes)
    for field in ("transcribed_seconds", "media_duration"):
        if status_data.get(field) is not None:
            response_data[field] = status_data[field]

    # Add child jobs info for main jobs
    if job_type == "main":
        # Get total_pages from MySQL first, fallback to Redis
        total_pages = None
        pages_completed = 0
        pages_failed = 0

        if db_job and db_job.total_pages:
            total_pages = db_job.total_pages
            pages_completed = db_job.pages_completed or 0
            pages_failed = db_job.pages_failed or 0
        else:
            # Fallback to Redis
            total_pages = redis_client.get_job_pages_total(job_id)
            if total_pages:
                pages_completed = redis_client.count_completed_page_jobs(job_id)
                pages_failed = redis_client.count_failed_page_jobs(job_id)

        if total_pages:
            response_data["total_pages"] = total_pages

            # Add detailed page status for each page
            pages_status_dict = {}  # Use dict for fast lookup by page number

            # Try MySQL first with pagination
            query = db.query(Page).filter(Page.job_id == job_id).order_by(Page.page_number)

            if page_limit is not None:
                query = query.limit(page_limit).offset(page_offset)

            db_pages = query.all()

            if db_pages:
                # Use MySQL data
                for db_page in db_pages:
                    # Map database status to schema status
                    status_map = {
                        DBJobStatus.PENDING: "pending",
                        DBJobStatus.PROCESSING: "processing",
                        DBJobStatus.COMPLETED: "completed",
                        DBJobStatus.FAILED: "failed",
                        DBJobStatus.CANCELLED: "failed",
                    }
                    page_status = status_map.get(db_page.status, "pending")

                    # No fabricated ids: a page row without `page_job_id` has no
                    # page job to address, and inventing one ("page-3") both
                    # failed schema validation (500) and pointed callers at a
                    # URL that 404s. `None` says what is true; the URL falls back
                    # to the by-page-number route, which is real either way.
                    pages_status_dict[db_page.page_number] = {
                        "page_number": db_page.page_number,
                        "job_id": db_page.page_job_id,
                        "status": page_status,
                        "url": (
                            f"/jobs/{db_page.page_job_id}/result"
                            if db_page.page_job_id
                            else f"/jobs/{job_id}/pages/{db_page.page_number}/result"
                        ),
                        "error_message": db_page.error_message,
                        "retry_count": db_page.retry_count or 0,
                    }
            else:
                # Fallback to Redis
                page_job_ids = redis_client.get_page_jobs(job_id)
                for page_job_id in page_job_ids:
                    page_status_data = redis_client.get_job_status(page_job_id)
                    if page_status_data:
                        page_num = page_status_data.get("page_number", 0)
                        pages_status_dict[page_num] = {
                            "page_number": page_num,
                            "job_id": page_job_id,
                            "status": page_status_data.get("status", "pending"),
                            "url": f"/jobs/{page_job_id}/result",
                            "error_message": page_status_data.get("error"),
                            "retry_count": 0,  # Redis doesn't track retry count
                        }

            # Build complete pages list with placeholders
            # If pagination is enabled, only include pages in the requested range
            if page_limit is not None:
                start_page = page_offset + 1
                end_page = min(page_offset + page_limit, total_pages)
            else:
                start_page = 1
                end_page = total_pages

            pages_status_list = []
            for page_num in range(start_page, end_page + 1):
                if page_num in pages_status_dict:
                    pages_status_list.append(pages_status_dict[page_num])
                else:
                    # Placeholder for pages the split task has not created yet.
                    # `job_id` stays None - there is no page job to point at.
                    pages_status_list.append({
                        "page_number": page_num,
                        "job_id": None,
                        "status": "queued",
                        "url": f"/jobs/{job_id}/pages/{page_num}/result",
                        "error_message": None,
                        "retry_count": 0,
                    })

            # Only recalculate counts if not already set from database
            # (pagination would make these counts wrong)
            if not db_job or not db_job.total_pages:
                pages_completed = sum(1 for p in pages_status_list if p["status"] == "completed")
                pages_failed = sum(1 for p in pages_status_list if p["status"] == "failed")

            response_data["pages_completed"] = pages_completed
            response_data["pages_failed"] = pages_failed
            response_data["pages"] = pages_status_list

        # Add child jobs information
        if "child_job_ids" in status_data and status_data["child_job_ids"]:
            child_jobs_data = status_data["child_job_ids"]
            response_data["child_jobs"] = ChildJobs(
                split_job_id=child_jobs_data.get("split_job_id"),
                page_job_ids=child_jobs_data.get("page_job_ids", []),
                merge_job_id=child_jobs_data.get("merge_job_id"),
            )

    return JobStatusResponse(**response_data)


@router.delete("/jobs/{job_id}", summary="Deletar job")
async def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    owned_job: Optional[Job] = Depends(get_owned_job),
    db: Session = Depends(get_db),
):
    """
    Deletar job e todos os seus dados associados

    Remove completamente um job do sistema, incluindo:
    - Metadados do MySQL (job e pages)
    - Conteúdo do Elasticsearch (markdown)
    - Status temporário do Redis
    - Para transcrições: o áudio/vídeo enviado e as transcrições guardadas no MinIO

    **Atenção:** Esta operação é irreversível!

    ## Para jobs MAIN com páginas:
    - Deleta o job principal
    - Deleta todos os jobs filhos (split, pages, merge)
    - Deleta todos os registros de páginas
    - Remove todo o conteúdo markdown

    ## Permissões:
    - Apenas o dono do job (verificado no MySQL) pode deletá-lo

    ## Retorno:
    - 200: Job deletado com sucesso
    - 404: Job não encontrado (também retornado quando o job pertence a outro
      usuário, para não expor a existência do recurso)
    """
    redis_client = get_redis_client()

    # Try to get ES client (may fail if ES is not available)
    es_client = None
    try:
        es_client = get_es_client()
    except Exception as e:
        logger.info(f"Elasticsearch not available: {e}")

    # Ownership já validada em get_owned_job (MySQL como fonte da verdade)
    status_data = redis_client.get_job_status(job_id)

    # Linha própria no MySQL (jobs filhos não são persistidos)
    db_job = owned_job if (owned_job is not None and owned_job.id == job_id) else None

    if not status_data and not db_job:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    logger.info(f"Deleting job {job_id} for user {current_user.username}")

    # 1. Delete from Elasticsearch (if available)
    if es_client:
        try:
            # Delete main job result
            es_client.delete_job_result(job_id)

            # Delete all page results
            es_client.delete_all_page_results(job_id)

            logger.info(f"Deleted job {job_id} from Elasticsearch")
        except Exception as e:
            # ES may not be available - that's OK
            logger.info(f"Failed to delete job {job_id} from Elasticsearch: {e}")
    else:
        logger.info(f"Elasticsearch not available, skipping content deletion for job {job_id}")

    # Transcriptions: the uploaded media and the stored transcript formats
    if db_job and db_job.source_type == "audio":
        try:
            minio_client = get_minio_client()
            if db_job.minio_upload_path:
                minio_client.delete_file(minio_client.bucket_audio, db_job.minio_upload_path)
            minio_client.delete_folder(minio_client.bucket_audio, f"transcripts/{job_id}/")
        except Exception as e:
            logger.warning(f"Failed to delete audio objects of job {job_id} from MinIO: {e}")
        # Local copy left behind by a failed job (a completed one has none)
        shutil.rmtree(Path(settings.temp_storage_path) / "audio" / job_id, ignore_errors=True)

    # 2. Delete from MySQL
    try:
        if db_job:
            # Get all child jobs (split, page, merge) to delete them too
            child_jobs = db.query(Job).filter(Job.parent_job_id == job_id).all()

            # Delete all pages associated with this job
            db.query(Page).filter(Page.job_id == job_id).delete()

            # Delete child jobs
            for child_job in child_jobs:
                db.delete(child_job)

            # Delete main job
            db.delete(db_job)
            db.commit()

            logger.info(f"Deleted job {job_id} and {len(child_jobs)} child jobs from MySQL")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete job {job_id} from MySQL: {e}")
        raise HTTPException(status_code=500, detail="Erro ao deletar do banco de dados")

    # 3. Delete from Redis
    try:
        # Get child job IDs from Redis
        child_job_ids_data = status_data.get("child_job_ids", {}) if status_data else {}

        # Delete page jobs
        page_job_ids = child_job_ids_data.get("page_job_ids", [])
        for page_job_id in page_job_ids:
            redis_client.delete_job(page_job_id)

        # Delete split job
        split_job_id = child_job_ids_data.get("split_job_id")
        if split_job_id:
            redis_client.delete_job(split_job_id)

        # Delete merge job
        merge_job_id = child_job_ids_data.get("merge_job_id")
        if merge_job_id:
            redis_client.delete_job(merge_job_id)

        # Delete main job
        redis_client.delete_job(job_id)

        # Remove from user's job list
        redis_client.remove_job_from_user(current_user.id, job_id)

        logger.info(f"Deleted job {job_id} from Redis")
    except Exception as e:
        logger.warning(f"Failed to delete job {job_id} from Redis: {e}")

    return {
        "message": "Job deletado com sucesso",
        "job_id": job_id,
        "deleted_at": datetime.utcnow().isoformat()
    }


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
async def get_job_result(
    job_id: str,
    format_: Optional[str] = Query(
        None,
        alias="format",
        description="Para transcrições: markdown (JSON padrão), vtt, srt, txt ou json. "
                    "Sem este parâmetro vale o output_format escolhido no /transcribe.",
    ),
    current_user: User = Depends(get_current_active_user),
    owned_job: Optional[Job] = Depends(get_owned_job),
    db: Session = Depends(get_db),
):
    """
    Recuperar resultado de qualquer tipo de job (main ou page individual)

    ## Permissões:
    - Apenas o dono do job (verificado no MySQL) pode acessar o resultado.
      Jobs de outros usuários retornam 404.

    Para jobs de transcrição (/transcribe), `?format=vtt|srt|txt|json` retorna o
    arquivo no formato pedido (ex.: legenda WebVTT com `Content-Type: text/vtt`).
    """
    if format_ is not None:
        format_ = format_.lower()
        if format_ not in ["markdown"] + TRANSCRIPT_FORMATS:
            raise HTTPException(
                status_code=422,
                detail=f"format inválido: {format_}. Use: markdown, {', '.join(TRANSCRIPT_FORMATS)}"
            )

    redis_client = get_redis_client()
    es_client = get_es_client()

    # Ownership já validada em get_owned_job (MySQL como fonte da verdade)

    # Check job status first
    status_data = redis_client.get_job_status(job_id)

    if not status_data:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado")

    if status_data["status"] == "processing" or status_data["status"] == "queued":
        raise HTTPException(status_code=400, detail="Job ainda está em processamento")

    if status_data["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Job falhou: {status_data.get('error', 'Erro desconhecido')}"
        )

    # Transcription formats (explicit ?format= or the default chosen at upload) are
    # served straight from Redis/MinIO, even if Elasticsearch has no result
    requested_format = format_ or redis_client.get_job_output_format(job_id)
    if requested_format and requested_format != "markdown":
        return _transcript_response(job_id, requested_format, redis_client)

    # Get job type
    job_type = status_data.get("type", "main")

    # Try to get result from Elasticsearch first
    result_data = None
    es_result = es_client.get_job_result(job_id)

    if es_result:
        logger.info(f"Retrieved job {job_id} result from Elasticsearch")
        result_data = {
            "markdown": es_result.get("markdown_content", ""),
            "metadata": es_result.get("metadata", {})
        }
    else:
        # Fallback to Redis for backwards compatibility
        logger.info(f"Result not in Elasticsearch, trying Redis for job {job_id}")
        redis_result = redis_client.get_job_result(job_id)
        if redis_result:
            result_data = redis_result
        else:
            raise HTTPException(status_code=404, detail="Resultado não encontrado ou expirado")

    # Older transcription jobs only have their default format in the result metadata
    if not requested_format:
        default_format = (result_data.get("metadata") or {}).get("output_format") or "markdown"
        if default_format != "markdown":
            return _transcript_response(job_id, default_format, redis_client)

    # Get completed_at timestamp
    completed_at = None
    db_job = owned_job if (owned_job is not None and owned_job.id == job_id) else None

    if db_job and db_job.completed_at:
        completed_at = db_job.completed_at
    elif "completed_at" in status_data and status_data["completed_at"]:
        completed_at = datetime.fromisoformat(status_data["completed_at"])
    else:
        completed_at = datetime.utcnow()

    # Build response
    response_data = {
        "job_id": job_id,
        "type": job_type,
        "status": "completed",
        "result": result_data,
        "completed_at": completed_at,
    }

    # Add page info for page jobs
    if job_type == "page":
        response_data["page_number"] = status_data.get("page_number")
        response_data["parent_job_id"] = status_data.get("parent_job_id")

    return JobResultResponse(**response_data)


def _transcript_response(job_id: str, fmt: str, redis_client) -> Response:
    """Return one transcript format (from Redis, or MinIO once the Redis result expired)"""
    content = ((redis_client.get_job_result(job_id) or {}).get("transcript") or {}).get(fmt)

    if content is None:
        try:
            minio_client = get_minio_client()
            data = minio_client.download_file(
                bucket_name=minio_client.bucket_audio,
                object_name=transcript_object_name(job_id, fmt),
            )
            content = data.decode("utf-8") if data is not None else None
        except Exception as e:
            logger.warning(f"Transcript {fmt} for job {job_id} not available in MinIO: {e}")

    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Formato '{fmt}' não disponível para este job (apenas jobs de /transcribe geram {', '.join(TRANSCRIPT_FORMATS)})"
        )

    return Response(
        content=content,
        media_type=TRANSCRIPT_CONTENT_TYPES[fmt],
        headers={"Content-Disposition": f'inline; filename="{job_id}.{fmt}"'},
    )


@router.get("/jobs/{job_id}/pages", response_model=JobPagesResponse)
async def get_job_pages(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    owned_job: Optional[Job] = Depends(get_owned_job),
    db: Session = Depends(get_db),
):
    """
    Obter progresso detalhado por página com job_id de cada página (para PDFs)

    ## Permissões:
    - Apenas o dono do job (verificado no MySQL) pode consultar as páginas.
      Jobs de outros usuários retornam 404.
    """
    redis_client = get_redis_client()

    # Ownership já validada em get_owned_job (MySQL como fonte da verdade)

    # Try to get pages from MySQL first
    db_pages = db.query(Page).filter(Page.job_id == job_id).order_by(Page.page_number).all()

    if db_pages:
        logger.info(f"Retrieved {len(db_pages)} pages from MySQL for job {job_id}")
        pages_list = []
        for db_page in db_pages:
            # Map database status to schema status
            status_map = {
                DBJobStatus.PENDING: "pending",
                DBJobStatus.PROCESSING: "processing",
                DBJobStatus.COMPLETED: "completed",
                DBJobStatus.FAILED: "failed",
                DBJobStatus.CANCELLED: "failed",
            }
            page_status = status_map.get(db_page.status, "pending")

            # Same rule as GET /jobs/{job_id}: never invent a page job id.
            pages_list.append(PageJobInfo(
                page_number=db_page.page_number,
                job_id=db_page.page_job_id,
                status=page_status,
                url=(
                    f"/jobs/{db_page.page_job_id}/result"
                    if db_page.page_job_id
                    else f"/jobs/{job_id}/pages/{db_page.page_number}/result"
                ),
                error_message=db_page.error_message,
                retry_count=db_page.retry_count or 0,
            ))

        total_pages = len(db_pages)
        pages_completed = sum(1 for p in db_pages if p.status == DBJobStatus.COMPLETED)
        pages_failed = sum(1 for p in db_pages if p.status == DBJobStatus.FAILED)

        return JobPagesResponse(
            job_id=job_id,
            total_pages=total_pages,
            pages_completed=pages_completed,
            pages_failed=pages_failed,
            pages=pages_list,
        )

    # Fallback to Redis
    logger.info(f"No pages in MySQL, trying Redis for job {job_id}")
    total_pages = redis_client.get_job_pages_total(job_id)

    if not total_pages:
        raise HTTPException(
            status_code=404,
            detail="Job não tem páginas (não é PDF multi-página ou não foi encontrado)"
        )

    # Get page job IDs from main job
    page_job_ids = redis_client.get_page_jobs(job_id)

    if not page_job_ids:
        # Edge case: total_pages exists but no page jobs were created
        # This happens when PDF was processed as a single document without splitting
        logger.warning(f"Job {job_id} has total_pages={total_pages} but no page jobs found")
        return JobPagesResponse(
            job_id=job_id,
            total_pages=total_pages,
            pages_completed=0,
            pages_failed=0,
            pages=[],
        )

    # Build page info list
    pages_list = []
    for page_job_id in page_job_ids:
        page_status_data = redis_client.get_job_status(page_job_id)

        if page_status_data:
            page_num = page_status_data.get("page_number", 0)
            pages_list.append(PageJobInfo(
                page_number=page_num,
                job_id=page_job_id,
                status=page_status_data.get("status", "pending"),
                url=f"/jobs/{page_job_id}/result",
                error_message=page_status_data.get("error"),
                retry_count=0,  # Redis doesn't track retry count
            ))

    # Sort by page number
    pages_list.sort(key=lambda p: p.page_number)

    # Calculate stats
    pages_completed = sum(1 for p in pages_list if p.status == "completed")
    pages_failed = sum(1 for p in pages_list if p.status == "failed")

    return JobPagesResponse(
        job_id=job_id,
        total_pages=total_pages,
        pages_completed=pages_completed,
        pages_failed=pages_failed,
        pages=pages_list,
    )


@router.get("/jobs/{job_id}/pages/{page_number}/status", summary="Status de página específica por número")
async def get_page_status_by_number(
    job_id: str,
    page_number: int,
    current_user: User = Depends(get_current_active_user),
    db_page: Optional[Page] = Depends(get_owned_page_or_none),
    db: Session = Depends(get_db),
):
    """
    Consulta o status de uma página específica usando o número da página

    ## Parâmetros:
    - `job_id`: ID do job principal
    - `page_number`: Número da página (1, 2, 3, ...)

    ## Retorno:
    Status da página específica

    ## Exemplo:
    ```
    GET /jobs/550e8400-e29b-41d4-a716-446655440000/pages/5/status
    ```

    Retorna o status da página 5 do job especificado.

    ## Permissões:
    - Apenas o dono do job (verificado no MySQL) pode consultar a página.
      Jobs de outros usuários retornam 404.
    """
    redis_client = get_redis_client()

    # Ownership já validada em get_owned_page_or_none -> get_owned_job
    # (MySQL como fonte da verdade). db_page vem da mesma dependência.

    if db_page:
        # Map database status to schema status
        status_map = {
            DBJobStatus.PENDING: "pending",
            DBJobStatus.PROCESSING: "processing",
            DBJobStatus.COMPLETED: "completed",
            DBJobStatus.FAILED: "failed",
            DBJobStatus.CANCELLED: "failed",
        }

        return {
            "job_id": db_page.page_job_id or f"page-{page_number}",
            "parent_job_id": job_id,
            "type": "page",
            "page_number": page_number,
            "status": status_map.get(db_page.status, "pending"),
            "started_at": db_page.created_at,
            "completed_at": db_page.completed_at,
            "error": db_page.error_message,
        }

    # Fallback to Redis
    page_job_id = redis_client.get_page_job_id_by_number(job_id, page_number)

    if not page_job_id:
        raise HTTPException(
            status_code=404,
            detail=f"Página {page_number} não encontrada no job {job_id}. "
                   f"Verifique se o job é um PDF multi-página e se a página existe."
        )

    # Buscar status do page job
    page_status = redis_client.get_job_status(page_job_id)

    if not page_status:
        raise HTTPException(status_code=404, detail="Status da página não encontrado")

    # Parse timestamps
    started_at = None
    completed_at = None

    if "started_at" in page_status and page_status["started_at"]:
        started_at = datetime.fromisoformat(page_status["started_at"])

    if "completed_at" in page_status and page_status["completed_at"]:
        completed_at = datetime.fromisoformat(page_status["completed_at"])

    return {
        "job_id": page_job_id,
        "parent_job_id": job_id,
        "type": "page",
        "page_number": page_number,
        "status": page_status.get("status"),
        "started_at": started_at,
        "completed_at": completed_at,
        "error": page_status.get("error"),
    }


@router.get("/jobs/{job_id}/pages/{page_number}/result", summary="Resultado de página específica por número")
async def get_page_result_by_number(
    job_id: str,
    page_number: int,
    current_user: User = Depends(get_current_active_user),
    db_page: Optional[Page] = Depends(get_owned_page_or_none),
    db: Session = Depends(get_db),
):
    """
    Recupera o resultado (markdown) de uma página específica usando o número da página

    ## Parâmetros:
    - `job_id`: ID do job principal
    - `page_number`: Número da página (1, 2, 3, ...)

    ## Retorno:
    Markdown da página específica

    ## Exemplo:
    ```
    GET /jobs/550e8400-e29b-41d4-a716-446655440000/pages/5/result
    ```

    Retorna o markdown da página 5 do job especificado.

    ## Vantagem:
    Não precisa conhecer o `page_job_id` - basta usar o job principal + número da página!

    ## Permissões:
    - Apenas o dono do job (verificado no MySQL) pode acessar o resultado.
      Jobs de outros usuários retornam 404.
    """
    redis_client = get_redis_client()
    es_client = get_es_client()

    # Ownership já validada em get_owned_page_or_none -> get_owned_job
    # (MySQL como fonte da verdade). db_page vem da mesma dependência.

    # Try to get page from Elasticsearch first
    es_page_result = es_client.get_page_result(job_id, page_number)

    if es_page_result:
        logger.info(f"Retrieved page {page_number} from Elasticsearch for job {job_id}")

        # Check status
        if db_page:
            if db_page.status == DBJobStatus.FAILED:
                raise HTTPException(
                    status_code=500,
                    detail=f"Conversão da página {page_number} falhou: {db_page.error_message or 'Erro desconhecido'}"
                )

            return {
                "job_id": db_page.page_job_id or f"page-{page_number}",
                "parent_job_id": job_id,
                "type": "page",
                "page_number": page_number,
                "status": "completed",
                "result": {
                    "markdown": es_page_result.get("markdown_content", ""),
                    "metadata": es_page_result.get("metadata", {})
                },
                "completed_at": db_page.completed_at or datetime.utcnow(),
            }
        else:
            # ES has data but MySQL doesn't - return ES data
            return {
                "job_id": f"page-{page_number}",
                "parent_job_id": job_id,
                "type": "page",
                "page_number": page_number,
                "status": "completed",
                "result": {
                    "markdown": es_page_result.get("markdown_content", ""),
                    "metadata": es_page_result.get("metadata", {})
                },
                "completed_at": es_page_result.get("created_at") or datetime.utcnow(),
            }

    # Fallback to Redis
    logger.info(f"Page {page_number} not in Elasticsearch, trying Redis for job {job_id}")
    page_job_id = redis_client.get_page_job_id_by_number(job_id, page_number)

    if not page_job_id:
        raise HTTPException(
            status_code=404,
            detail=f"Página {page_number} não encontrada no job {job_id}. "
                   f"Verifique se o job é um PDF multi-página e se a página existe."
        )

    # Verificar status primeiro
    page_status = redis_client.get_job_status(page_job_id)

    if not page_status:
        raise HTTPException(status_code=404, detail="Status da página não encontrado")

    if page_status["status"] in ["processing", "queued"]:
        raise HTTPException(
            status_code=400,
            detail=f"Página {page_number} ainda está em processamento (status: {page_status['status']})"
        )

    if page_status["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Conversão da página {page_number} falhou: {page_status.get('error', 'Erro desconhecido')}"
        )

    # Buscar resultado
    result_data = redis_client.get_job_result(page_job_id)

    if not result_data:
        raise HTTPException(
            status_code=404,
            detail=f"Resultado da página {page_number} não encontrado ou expirado"
        )

    completed_at = None
    if "completed_at" in page_status and page_status["completed_at"]:
        completed_at = datetime.fromisoformat(page_status["completed_at"])

    return {
        "job_id": page_job_id,
        "parent_job_id": job_id,
        "type": "page",
        "page_number": page_number,
        "status": "completed",
        "result": result_data,
        "completed_at": completed_at or datetime.utcnow(),
    }


# `kind` of a job, derived from Job.source_type: what the user sees it as.
JOB_KINDS = ("document", "transcription", "image")
_KIND_SOURCE_TYPES = {"transcription": "audio", "image": "image"}

# MySQL's PENDING is the API's "queued".
_DB_TO_API_STATUS = {
    DBJobStatus.PENDING: "queued",
    DBJobStatus.PROCESSING: "processing",
    DBJobStatus.COMPLETED: "completed",
    DBJobStatus.FAILED: "failed",
    DBJobStatus.CANCELLED: "cancelled",
}
_API_TO_DB_STATUS = {api: db for db, api in _DB_TO_API_STATUS.items()}


def job_kind(source_type: Optional[str]) -> str:
    for kind, st in _KIND_SOURCE_TYPES.items():
        if source_type == st:
            return kind
    return "document"


@router.get("/jobs", summary="Listar jobs do usuário")
async def list_jobs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    job_type: str = "main",
    tag: Optional[List[str]] = Query(None, description="Só jobs com esta tag. Repita para exigir várias (E)."),
    q: Optional[str] = Query(None, description="Busca no nome e no nome do arquivo (não no conteúdo; para isso use /search)."),
    kind: Optional[str] = Query(None, description="document, transcription ou image"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Lista os jobs do usuário autenticado, do mais recente para o mais antigo.

    A lista vem do MySQL (fonte da verdade); o Redis só complementa o status e
    o progresso ao vivo dos jobs em andamento.

    ## Parâmetros:
    - `limit`: Máximo de jobs (padrão: 50, máximo: 100)
    - `offset`: Quantos pular (paginação)
    - `status`: queued, processing, completed, failed ou cancelled
    - `tag`: Filtra por tag; `?tag=a&tag=b` exige as duas
    - `q`: Texto no nome do job ou do arquivo
    - `kind`: `document`, `transcription` ou `image`
    - `job_type`: `main` (padrão) ou `all`

    ## Retorno:
    `{total, limit, offset, jobs, counts}`. `total` é o total filtrado antes da
    paginação; `counts` traz quantos jobs há em cada status com os demais
    filtros aplicados (para montar os filtros da interface).
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    if status is not None and status not in _API_TO_DB_STATUS:
        raise HTTPException(status_code=422, detail=f"status inválido: {status}")
    if kind is not None and kind not in JOB_KINDS:
        raise HTTPException(status_code=422, detail=f"kind inválido: {kind}. Use: {', '.join(JOB_KINDS)}")
    tag_filter = parse_tags_or_422(tag)

    query = db.query(Job).filter(Job.user_id == current_user.id)
    if job_type != "all":
        query = query.filter(func.upper(Job.job_type) == job_type.upper())
    for t in tag_filter:
        query = query.filter(Job.tag_rows.any(JobTag.tag == t))
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Job.name.ilike(like), Job.filename.ilike(like)))
    if kind == "document":
        query = query.filter(or_(Job.source_type.is_(None), Job.source_type.notin_(list(_KIND_SOURCE_TYPES.values()))))
    elif kind is not None:
        query = query.filter(Job.source_type == _KIND_SOURCE_TYPES[kind])

    counts = {"all": 0, **{api: 0 for api in _API_TO_DB_STATUS}}
    for db_status, n in query.with_entities(Job.status, func.count(Job.id)).group_by(Job.status).all():
        counts[_DB_TO_API_STATUS.get(db_status, "queued")] += n
        counts["all"] += n

    if status is not None:
        query = query.filter(Job.status == _API_TO_DB_STATUS[status])

    total = query.count()
    rows = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()

    redis_client = get_redis_client()
    jobs = []
    for job in rows:
        job_id = str(job.id)
        db_status = _DB_TO_API_STATUS.get(job.status, "queued")
        live = None
        if db_status in ("queued", "processing"):
            try:
                live = redis_client.get_job_status(job_id)
            except Exception as e:
                logger.warning(f"Redis unavailable for job {job_id} status: {e}")

        item = {
            "job_id": job_id,
            "type": (job.job_type or "main").lower(),
            "status": (live or {}).get("status") or db_status,
            "progress": (live or {}).get("progress", 100 if db_status == "completed" else (job.progress or 0)),
            "name": job.name or job.filename,
            "filename": job.filename,
            "kind": job_kind(job.source_type),
            "source_type": job.source_type,
            "mime_type": job.mime_type,
            "file_size_bytes": job.file_size_bytes,
            "tags": job.tags,
            "error": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
        if job.total_pages:
            item["total_pages"] = job.total_pages
            item["pages_completed"] = job.pages_completed or 0
        jobs.append(item)

    return {"total": total, "limit": limit, "offset": offset, "jobs": jobs, "counts": counts}


@router.get("/search", summary="Buscar jobs por conteúdo")
async def search_jobs(
    query: str,
    limit: int = 10,
    current_user: User = Depends(get_current_active_user),
):
    """
    Buscar jobs por conteúdo do markdown usando Elasticsearch

    ## Parâmetros:
    - `query`: Texto a buscar no conteúdo dos documentos
    - `limit`: Número máximo de resultados (padrão: 10, máximo: 100)

    ## Retorno:
    Lista de jobs que contêm o texto buscado no conteúdo convertido

    ## Exemplos:
    - `/search?query=relatório financeiro` - Busca jobs contendo "relatório financeiro"
    - `/search?query=invoice&limit=20` - Busca jobs contendo "invoice", até 20 resultados
    """
    es_client = get_es_client()

    # Validate limit
    if limit > 100:
        limit = 100

    try:
        # Search in Elasticsearch, filtered by current user
        results = es_client.search_jobs(
            query=query,
            user_id=current_user.id,
            limit=limit
        )

        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "job_id": result.get("job_id"),
                "filename": result.get("filename"),
                "total_pages": result.get("total_pages"),
                "char_count": result.get("char_count"),
                "created_at": result.get("created_at"),
                "preview": result.get("markdown_content", "")[:200] + "..."  # First 200 chars as preview
            })

        return {
            "query": query,
            "total": len(formatted_results),
            "limit": limit,
            "results": formatted_results,
        }

    except Exception as e:
        logger.error(f"Error searching jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao buscar jobs")


@router.post("/jobs/{job_id}/pages/{page_number}/retry", summary="Retry de página que falhou")
async def retry_failed_page(
    job_id: str,
    page_number: int,
    current_user: User = Depends(get_current_active_user),
    owned_job: Optional[Job] = Depends(get_owned_job),
    db_page: Optional[Page] = Depends(get_owned_page_or_none),
    db: Session = Depends(get_db),
):
    """
    Tenta reprocessar uma página que falhou

    ## Parâmetros:
    - `job_id`: ID do job principal
    - `page_number`: Número da página que falhou

    ## Retorno:
    Novo job_id da página em retry

    ## Exemplo:
    ```
    POST /jobs/550e8400-e29b-41d4-a716-446655440000/pages/5/retry
    ```

    Reprocessa a página 5 do job especificado.

    ## Permissões:
    - Apenas o dono do job (verificado no MySQL) pode reprocessar a página.
      Jobs de outros usuários retornam 404.
    """
    redis_client = get_redis_client()

    # Ownership já validada em get_owned_page_or_none -> get_owned_job
    # (MySQL como fonte da verdade). db_page vem da mesma dependência.

    # If page doesn't exist in MySQL, try to get it from Redis (backwards compatibility)
    if not db_page:
        # Try to find the page job in Redis
        page_job_id = redis_client.get_page_job_id_by_number(job_id, page_number)

        if page_job_id:
            # Get page status from Redis
            page_status = redis_client.get_job_status(page_job_id)

            if not page_status or page_status.get("status") != "failed":
                raise HTTPException(
                    status_code=400,
                    detail=f"Página {page_number} não está em status 'failed' (status: {page_status.get('status') if page_status else 'unknown'})"
                )

            # Create the page record in MySQL for future tracking
            try:
                from uuid import uuid4
                db_page = Page(
                    id=str(uuid4()),
                    job_id=job_id,
                    page_number=page_number,
                    page_job_id=page_job_id,
                    status=DBJobStatus.FAILED,
                    error_message=page_status.get("error", "Unknown error")
                )
                db.add(db_page)
                db.commit()
                logger.info(f"Created Page record in MySQL for page {page_number} (migrated from Redis)")
            except Exception as e:
                logger.error(f"Failed to create Page record: {e}")
                db.rollback()
                # Continue anyway - we can still retry using Redis data
        else:
            raise HTTPException(status_code=404, detail=f"Página {page_number} não encontrada no job {job_id}")
    else:
        # Check if page actually failed
        if db_page.status != DBJobStatus.FAILED:
            raise HTTPException(
                status_code=400,
                detail=f"Página {page_number} não está em status 'failed' (status atual: {db_page.status.value})"
            )

        # Check retry limit (max 3 attempts)
        if db_page.retry_count >= 3:
            raise HTTPException(
                status_code=400,
                detail=f"Limite de tentativas atingido para página {page_number} (3/3 tentativas). Não é possível tentar novamente."
            )

    # Get main job info to access original file
    db_job = owned_job if (owned_job is not None and owned_job.id == job_id) else None
    if not db_job:
        raise HTTPException(status_code=404, detail="Job principal não encontrado")

    logger.info(f"Retrying page {page_number} of job {job_id} for user {current_user.username}")

    try:
        from workers.tasks import process_page
        from pathlib import Path
        import uuid

        # Generate new job ID for the retry
        new_page_job_id = str(uuid.uuid4())

        # Update page status to pending and increment retry count
        db_page.status = DBJobStatus.PENDING
        db_page.page_job_id = new_page_job_id
        db_page.error_message = None
        db_page.retry_count += 1
        db.commit()

        logger.info(f"Retry attempt {db_page.retry_count}/3 for page {page_number}")

        # Create Redis status for new page job
        redis_client.set_job_status(
            job_id=new_page_job_id,
            job_type="page",
            status="queued",
            progress=0,
            parent_job_id=job_id,
            page_number=page_number,
        )

        # Set job ownership
        redis_client.set_job_owner(new_page_job_id, current_user.id)

        # Find the PDF file path
        # For file uploads, files are stored in temp_storage_path/uploads/{job_id}/
        settings = get_settings()
        temp_dir = Path(settings.temp_storage_path) / "uploads" / job_id

        # Find PDF file in directory
        pdf_files = list(temp_dir.glob("*.pdf"))

        # Local copies are deleted once a job completes: restore the original from MinIO
        if not pdf_files and db_job.minio_upload_path:
            try:
                restored = temp_dir / Path(db_job.minio_upload_path).name
                temp_dir.mkdir(parents=True, exist_ok=True)
                minio_client = get_minio_client()
                minio_client.download_file(
                    minio_client.bucket_uploads, db_job.minio_upload_path, file_path=str(restored)
                )
                pdf_files = [restored] if restored.suffix.lower() == ".pdf" else []
            except Exception as e:
                logger.warning(f"Could not restore original PDF of job {job_id} from MinIO: {e}")

        if not pdf_files:
            raise HTTPException(
                status_code=404,
                detail="Arquivo PDF original não encontrado. O arquivo pode ter expirado."
            )

        pdf_path = str(pdf_files[0])

        # Enqueue retry task
        process_page.delay(
            job_id=new_page_job_id,
            parent_job_id=job_id,
            pdf_path=pdf_path,
            page_number=page_number,
        )

        logger.info(f"Page {page_number} of job {job_id} enqueued for retry with new job_id {new_page_job_id}")

        return {
            "message": f"Página {page_number} enfileirada para reprocessamento (tentativa {db_page.retry_count}/3)",
            "job_id": job_id,
            "page_number": page_number,
            "new_page_job_id": new_page_job_id,
            "status": "queued",
            "retry_count": db_page.retry_count,
            "retry_limit": 3,
        }

    except ImportError as e:
        logger.error(f"Celery tasks not available: {e}")
        db.rollback()
        raise HTTPException(status_code=503, detail="Sistema de processamento indisponível")
    except Exception as e:
        logger.error(f"Error retrying page {page_number} of job {job_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao reprocessar página")


@router.get("/jobs/{job_id}/pages/{page_number}/pdf", summary="URL temporária do PDF de uma página")
async def get_page_pdf(
    job_id: str,
    page_number: int,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db_page: Optional[Page] = Depends(get_owned_page_or_none),
):
    """
    Devolve uma **URL pré-assinada de curta duração** para o PDF de uma página.

    ## Autenticação
    Obrigatória. Só o dono do job (verificado no MySQL) recebe a URL; jobs de
    outros usuários retornam 404, igual aos demais endpoints de job.

    Este endpoint já foi público e redirecionava (307) para uma URL pública do
    MinIO — quem tivesse um UUID de job lia o PDF de qualquer usuário. Agora o
    bucket é privado e o acesso é sempre por URL assinada com TTL curto.

    ## Parâmetros:
    - `job_id`: ID do job principal
    - `page_number`: Número da página (1-indexed)

    ## Retorno (JSON, não é mais um redirect):
    ```json
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "page_number": 5,
      "url": "http://127.0.0.1:9000/ingestify-pages/pages/<job_id>/page_0005.pdf?X-Amz-...",
      "expires_in": 900,
      "expires_at": "2026-08-26T12:15:00+00:00"
    }
    ```

    - `url`: URL assinada, para ser buscada **diretamente** pelo navegador. Não
      aceita header `Authorization` (e não precisa dele).
    - `expires_in`: validade em segundos a partir de agora.
    - `expires_at`: instante de expiração em UTC (ISO-8601). O cliente deve
      pedir uma URL nova depois disso em vez de reutilizar a antiga.

    Um redirect não serviria: o header `Authorization` do chamador não sobrevive
    ao salto para o MinIO, e o cliente precisa saber quando a URL expira.

    ## Atenção
    A query string faz parte da assinatura — acrescentar qualquer parâmetro
    (`?t=<timestamp>`, por exemplo) invalida a URL e gera 403 no MinIO.
    """
    # Ownership já validada em get_owned_page_or_none -> get_owned_job
    # (MySQL como fonte da verdade).
    if not db_page:
        raise HTTPException(status_code=404, detail=f"Página {page_number} não encontrada")

    minio_client = get_minio_client()

    # If page has MinIO path stored, use it
    if db_page.minio_page_path:
        minio_object_path = db_page.minio_page_path
    else:
        # Fallback to expected path pattern
        minio_object_path = f"pages/{job_id}/page_{page_number:04d}.pdf"

    # Check if file exists in MinIO
    if not minio_client.file_exists(minio_client.bucket_pages, minio_object_path):
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo PDF da página {page_number} não encontrado no MinIO. O job pode não ter sido dividido em páginas."
        )

    # O host da requisição serve para descobrir o endereço do MinIO visível pelo
    # navegador quando MINIO_PUBLIC_ENDPOINT não está configurado. A assinatura
    # cobre esse host, por isso ele precisa ser o mesmo que o navegador usará.
    request_host = request.headers.get("host")

    expires = timedelta(seconds=PAGE_PDF_URL_TTL_SECONDS)
    expires_at = datetime.now(timezone.utc) + expires

    try:
        presigned_url = minio_client.get_presigned_url(
            minio_client.bucket_pages,
            minio_object_path,
            expires=expires,
            request_host=request_host,
        )
    except Exception as e:
        logger.error(
            f"Failed to sign URL for page {page_number} of job {job_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="Armazenamento de arquivos indisponível")

    logger.info(
        f"Issued presigned PDF URL for page {page_number} of job {job_id} "
        f"to user {current_user.id} (ttl {PAGE_PDF_URL_TTL_SECONDS}s)"
    )

    return {
        "job_id": job_id,
        "page_number": page_number,
        "url": presigned_url,
        "expires_in": PAGE_PDF_URL_TTL_SECONDS,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint"""
    redis_client = get_redis_client()
    es_client = get_es_client()

    # Check Redis
    redis_ok = redis_client.ping()

    # Check Elasticsearch
    es_ok = es_client.health_check()

    # Check Celery workers
    worker_count = 0
    try:
        from workers.celery_app import celery_app
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        worker_count = len(stats) if stats else 0
    except Exception as e:
        logger.warning(f"Could not check Celery workers: {e}")

    # Determine overall status
    if redis_ok and es_ok and worker_count > 0:
        status = "healthy"
    elif redis_ok and worker_count > 0:
        status = "degraded"  # ES down but can still work
    else:
        status = "unhealthy"

    response = HealthCheckResponse(
        status=status,
        redis=redis_ok,
        workers={
            "active": worker_count,
            "available": worker_count,
            "elasticsearch": es_ok,
        },
        timestamp=datetime.utcnow(),
    )

    # Return 503 if unhealthy
    if status == "unhealthy":
        raise HTTPException(status_code=503, detail=response.dict())

    return response
