from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Body, Depends
from typing import Optional, List
from uuid import uuid4
from datetime import datetime
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
from shared.database import SessionLocal, get_db
from shared.models import Job, Page, JobStatus as DBJobStatus, User
from shared.config import get_settings
from shared.auth import get_current_active_user
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Conversion"])
settings = get_settings()


@router.post("/upload", response_model=JobCreatedResponse, summary="Upload e converter arquivo")
async def upload_and_convert(
    file: UploadFile = File(..., description="Arquivo para conversão (PDF, DOCX, HTML, etc.)"),
    name: Optional[str] = Form(None, description="Nome de identificação (opcional, padrão: nome do arquivo)"),
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

    ## Formatos suportados
    PDF, DOCX, DOC, HTML, PPTX, XLSX, RTF, ODT

    ## Retorno
    Retorna imediatamente um `job_id` para consultar o progresso via `/jobs/{job_id}`

    ## Exemplo com nome customizado:
    ```bash
    curl -X POST http://localhost:8080/upload \
      -F "file=@documento.pdf" \
      -F "name=Relatório Mensal 2025"
    ```
    """
    redis_client = get_redis_client()

    # Read file contents
    file_contents = await file.read()
    filename = file.filename
    file_size_mb = len(file_contents) / (1024 * 1024)
    file_size_bytes = len(file_contents)

    # Validate file size
    if file_size_mb > settings.max_file_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande: {file_size_mb:.2f}MB. Máximo: {settings.max_file_size_mb}MB"
        )

    logger.info(f"File uploaded: {filename} ({file_size_mb:.2f}MB)")

    # Generate job ID
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
            source_type="file",
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            status=DBJobStatus.PENDING,
            job_type="MAIN",
            created_at=created_at,
        )
        db.add(db_job)
        db.commit()
        logger.info(f"Job {job_id} created in MySQL")
    except Exception as e:
        logger.error(f"Error creating job in MySQL: {e}", exc_info=True)
        db.rollback()
        # Continue - MySQL is for persistence, Redis is primary

    logger.info(f"MAIN JOB created: {job_id} | user: {current_user.username} | source_type: file")

    # Save file temporarily
    try:
        from workers.tasks import process_conversion
        from pathlib import Path

        temp_dir = Path(settings.temp_storage_path) / "uploads" / str(job_id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file_path = temp_dir / filename

        with open(temp_file_path, "wb") as f:
            f.write(file_contents)

        logger.info(f"File saved to: {temp_file_path}")

        # Enqueue task
        process_conversion.delay(
            job_id=str(job_id),
            source_type="file",
            source=str(temp_file_path),
            options={},
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
        raise HTTPException(status_code=500, detail=f"Erro ao criar job: {str(e)}")

    return JobCreatedResponse(
        job_id=job_id,
        status="queued",
        created_at=created_at,
        message="Job enfileirado para processamento"
    )


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

    # Validate source for non-file types
    if source_type != "file" and not source:
        raise HTTPException(status_code=400, detail=f"source é obrigatório para source_type={source_type}")

    # Validate authentication for gdrive and dropbox
    if source_type in ["gdrive", "dropbox"] and not authorization:
        raise HTTPException(status_code=401, detail="Authorization header é obrigatório para esta fonte")

    # Generate job ID
    job_id = uuid4()
    created_at = datetime.utcnow()

    # Read file contents if uploaded
    file_contents = None
    filename = None
    file_size_bytes = 0
    mime_type = None

    if file:
        file_contents = await file.read()
        filename = file.filename
        file_size_mb = len(file_contents) / (1024 * 1024)
        file_size_bytes = len(file_contents)
        mime_type = file.content_type or "application/octet-stream"

        # Validate file size
        if file_size_mb > settings.max_file_size_mb:
            raise HTTPException(
                status_code=413,
                detail=f"Arquivo muito grande: {file_size_mb:.2f}MB. Máximo: {settings.max_file_size_mb}MB"
            )

        logger.info(f"File uploaded: {filename} ({file_size_mb:.2f}MB)")

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
            source_type=source_type,
            source_url=source if source_type != "file" else None,
            file_size_bytes=file_size_bytes if file_size_bytes > 0 else None,
            mime_type=mime_type,
            status=DBJobStatus.PENDING,
            job_type="MAIN",
            created_at=created_at,
        )
        db.add(db_job)
        db.commit()
        logger.info(f"Job {job_id} created in MySQL (source_type: {source_type})")
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

        # Save file temporarily if uploaded
        if file_contents:
            temp_dir = Path(settings.temp_storage_path) / "uploads" / str(job_id)
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / filename

            with open(temp_file_path, "wb") as f:
                f.write(file_contents)

            task_kwargs["source"] = str(temp_file_path)
            logger.info(f"File saved to: {temp_file_path}")

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
        raise HTTPException(status_code=500, detail=f"Erro ao criar job: {str(e)}")

    return JobCreatedResponse(
        job_id=job_id,
        status="queued",
        created_at=created_at,
        message="Job enfileirado para processamento"
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Consultar status de qualquer tipo de job (main, split, page, merge)"""
    redis_client = get_redis_client()

    # Get job status from Redis (real-time data)
    status_data = redis_client.get_job_status(job_id)

    if not status_data:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado")

    # Verify job ownership
    if not redis_client.verify_job_ownership(job_id, current_user.id):
        raise HTTPException(status_code=403, detail="Acesso negado: este job pertence a outro usuário")

    # Get job metadata from MySQL
    db_job = db.query(Job).filter(Job.id == job_id).first()

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

    # Get job type
    job_type = status_data.get("type", "main")

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
        "name": status_data.get("name"),
    }

    # Add parent_job_id for child jobs (split, page, merge)
    if "parent_job_id" in status_data:
        response_data["parent_job_id"] = status_data["parent_job_id"]

    # Add page_number for page jobs
    if "page_number" in status_data:
        response_data["page_number"] = status_data["page_number"]

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
            response_data["pages_completed"] = pages_completed
            response_data["pages_failed"] = pages_failed

            # Add detailed page status for each page
            pages_status_list = []

            # Try MySQL first
            db_pages = db.query(Page).filter(Page.job_id == job_id).order_by(Page.page_number).all()

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

                    pages_status_list.append({
                        "page_number": db_page.page_number,
                        "job_id": db_page.page_job_id or f"page-{db_page.page_number}",
                        "status": page_status,
                        "url": f"/jobs/{db_page.page_job_id or job_id}/result",
                    })
            else:
                # Fallback to Redis
                page_job_ids = redis_client.get_page_jobs(job_id)
                for page_job_id in page_job_ids:
                    page_status_data = redis_client.get_job_status(page_job_id)
                    if page_status_data:
                        pages_status_list.append({
                            "page_number": page_status_data.get("page_number", 0),
                            "job_id": page_job_id,
                            "status": page_status_data.get("status", "pending"),
                            "url": f"/jobs/{page_job_id}/result",
                        })

                # Sort by page number
                pages_status_list.sort(key=lambda p: p["page_number"])

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
    db: Session = Depends(get_db),
):
    """
    Deletar job e todos os seus dados associados

    Remove completamente um job do sistema, incluindo:
    - Metadados do MySQL (job e pages)
    - Conteúdo do Elasticsearch (markdown)
    - Status temporário do Redis

    **Atenção:** Esta operação é irreversível!

    ## Para jobs MAIN com páginas:
    - Deleta o job principal
    - Deleta todos os jobs filhos (split, pages, merge)
    - Deleta todos os registros de páginas
    - Remove todo o conteúdo markdown

    ## Permissões:
    - Apenas o dono do job pode deletá-lo

    ## Retorno:
    - 200: Job deletado com sucesso
    - 403: Acesso negado (job de outro usuário)
    - 404: Job não encontrado
    """
    redis_client = get_redis_client()

    # Try to get ES client (may fail if ES is not available)
    es_client = None
    try:
        es_client = get_es_client()
    except Exception as e:
        logger.info(f"Elasticsearch not available: {e}")

    # Verify job exists and ownership
    status_data = redis_client.get_job_status(job_id)

    # Also check MySQL
    db_job = db.query(Job).filter(Job.id == job_id).first()

    if not status_data and not db_job:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    # Verify ownership
    if status_data and not redis_client.verify_job_ownership(job_id, current_user.id):
        raise HTTPException(status_code=403, detail="Acesso negado: este job pertence a outro usuário")

    if db_job and db_job.user_id and db_job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado: este job pertence a outro usuário")

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
        raise HTTPException(status_code=500, detail=f"Erro ao deletar do banco de dados: {str(e)}")

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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Recuperar resultado de qualquer tipo de job (main ou page individual)"""
    redis_client = get_redis_client()
    es_client = get_es_client()

    # Check job status first
    status_data = redis_client.get_job_status(job_id)

    if not status_data:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado")

    # Verify job ownership
    if not redis_client.verify_job_ownership(job_id, current_user.id):
        raise HTTPException(status_code=403, detail="Acesso negado: este job pertence a outro usuário")

    if status_data["status"] == "processing" or status_data["status"] == "queued":
        raise HTTPException(status_code=400, detail="Job ainda está em processamento")

    if status_data["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Job falhou: {status_data.get('error', 'Erro desconhecido')}"
        )

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

    # Get completed_at timestamp
    completed_at = None
    db_job = db.query(Job).filter(Job.id == job_id).first()

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


@router.get("/jobs/{job_id}/pages", response_model=JobPagesResponse)
async def get_job_pages(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Obter progresso detalhado por página com job_id de cada página (para PDFs)"""
    redis_client = get_redis_client()

    # Verify job ownership
    if not redis_client.verify_job_ownership(job_id, current_user.id):
        raise HTTPException(status_code=403, detail="Acesso negado: este job pertence a outro usuário")

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

            pages_list.append(PageJobInfo(
                page_number=db_page.page_number,
                job_id=db_page.page_job_id or f"page-{db_page.page_number}",
                status=page_status,
                url=f"/jobs/{db_page.page_job_id or job_id}/result",
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
        raise HTTPException(status_code=404, detail="Page jobs não encontrados")

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
    """
    redis_client = get_redis_client()

    # Verify job ownership
    if not redis_client.verify_job_ownership(job_id, current_user.id):
        raise HTTPException(status_code=403, detail="Acesso negado: este job pertence a outro usuário")

    # Try MySQL first
    db_page = db.query(Page).filter(
        Page.job_id == job_id,
        Page.page_number == page_number
    ).first()

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
    """
    redis_client = get_redis_client()
    es_client = get_es_client()

    # Verify job ownership
    if not redis_client.verify_job_ownership(job_id, current_user.id):
        raise HTTPException(status_code=403, detail="Acesso negado: este job pertence a outro usuário")

    # Try to get page from Elasticsearch first
    es_page_result = es_client.get_page_result(job_id, page_number)

    if es_page_result:
        logger.info(f"Retrieved page {page_number} from Elasticsearch for job {job_id}")

        # Get page metadata from MySQL
        db_page = db.query(Page).filter(
            Page.job_id == job_id,
            Page.page_number == page_number
        ).first()

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


@router.get("/jobs", summary="Listar jobs do usuário")
async def list_jobs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Lista jobs do usuário autenticado

    ## Parâmetros:
    - `limit`: Número máximo de jobs a retornar (padrão: 50, máximo: 100)
    - `offset`: Quantidade de jobs a pular (paginação)
    - `status`: Filtrar por status: queued, processing, completed, failed
    - `job_type`: Filtrar por tipo: main, page, split, merge

    ## Retorno:
    Lista de jobs com seus IDs, status e informações básicas

    ## Exemplos:
    - `/jobs` - Lista todos os jobs
    - `/jobs?job_type=main` - Apenas jobs principais (recomendado)
    - `/jobs?status=processing` - Apenas jobs em processamento
    - `/jobs?job_type=main&status=completed&limit=10` - Últimos 10 jobs principais completados
    """
    redis_client = get_redis_client()

    # Validate limit
    if limit > 100:
        limit = 100

    # Get all job keys from Redis
    try:
        # Get only jobs belonging to current user
        user_job_ids = redis_client.get_user_jobs(current_user.id, limit=1000)

        if not user_job_ids:
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "jobs": [],
            }

        # Get status for each job
        jobs_list = []
        for job_id in user_job_ids:
            status_data = redis_client.get_job_status(job_id)
            if status_data:
                # Filter by job_type if specified
                if job_type and status_data.get("type") != job_type:
                    continue

                # Filter by status if specified
                if status and status_data.get("status") != status:
                    continue

                job_info = {
                    "job_id": job_id,
                    "type": status_data.get("type", "main"),
                    "status": status_data.get("status"),
                    "progress": status_data.get("progress", 0),
                    "name": status_data.get("name"),
                }

                # Add total_pages for main jobs if available
                if status_data.get("type") == "main":
                    total_pages = redis_client.get_job_pages_total(job_id)
                    if total_pages:
                        job_info["total_pages"] = total_pages
                        job_info["pages_completed"] = redis_client.count_completed_page_jobs(job_id)

                # Add page_number for page jobs
                if status_data.get("type") == "page":
                    job_info["page_number"] = status_data.get("page_number")
                    job_info["parent_job_id"] = status_data.get("parent_job_id")

                jobs_list.append(job_info)

        # Sort by job_id (most recent first, assuming UUID v4 with timestamp component)
        jobs_list.sort(key=lambda x: x["job_id"], reverse=True)

        # Apply pagination
        paginated_jobs = jobs_list[offset : offset + limit]

        return {
            "total": len(jobs_list),
            "limit": limit,
            "offset": offset,
            "jobs": paginated_jobs,
        }

    except Exception as e:
        logger.error(f"Error listing jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao listar jobs: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Erro ao buscar jobs: {str(e)}")


@router.post("/jobs/{job_id}/pages/{page_number}/retry", summary="Retry de página que falhou")
async def retry_failed_page(
    job_id: str,
    page_number: int,
    current_user: User = Depends(get_current_active_user),
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
    """
    redis_client = get_redis_client()

    # Verify job ownership
    if not redis_client.verify_job_ownership(job_id, current_user.id):
        raise HTTPException(status_code=403, detail="Acesso negado: este job pertence a outro usuário")

    # Get page from MySQL
    db_page = db.query(Page).filter(
        Page.job_id == job_id,
        Page.page_number == page_number
    ).first()

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

    # Get main job info to access original file
    db_job = db.query(Job).filter(Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job principal não encontrado")

    logger.info(f"Retrying page {page_number} of job {job_id} for user {current_user.username}")

    try:
        from workers.tasks import process_page
        from pathlib import Path
        import uuid

        # Generate new job ID for the retry
        new_page_job_id = str(uuid.uuid4())

        # Update page status to pending
        db_page.status = DBJobStatus.PENDING
        db_page.page_job_id = new_page_job_id
        db_page.error_message = None
        db.commit()

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
            "message": f"Página {page_number} enfileirada para reprocessamento",
            "job_id": job_id,
            "page_number": page_number,
            "new_page_job_id": new_page_job_id,
            "status": "queued",
        }

    except ImportError as e:
        logger.error(f"Celery tasks not available: {e}")
        db.rollback()
        raise HTTPException(status_code=503, detail="Sistema de processamento indisponível")
    except Exception as e:
        logger.error(f"Error retrying page {page_number} of job {job_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao reprocessar página: {str(e)}")


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
