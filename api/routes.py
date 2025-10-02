from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Body
from typing import Optional
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
from shared.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Conversion"])
settings = get_settings()


@router.post("/upload", response_model=JobCreatedResponse, summary="Upload e converter arquivo")
async def upload_and_convert(
    file: UploadFile = File(..., description="Arquivo para conversão (PDF, DOCX, HTML, etc.)"),
    name: Optional[str] = Form(None, description="Nome de identificação (opcional, padrão: nome do arquivo)"),
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

    # Store initial job status in Redis
    redis_client.set_job_status(
        job_id=str(job_id),
        job_type="main",
        status="queued",
        progress=0,
        name=job_name,
    )

    logger.info(f"MAIN JOB created: {job_id} | source_type: file")

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
    if file:
        file_contents = await file.read()
        filename = file.filename
        file_size_mb = len(file_contents) / (1024 * 1024)

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

    logger.info(f"MAIN JOB created: {job_id} | source_type: {source_type}")

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
        raise HTTPException(status_code=500, detail=f"Erro ao criar job: {str(e)}")

    return JobCreatedResponse(
        job_id=job_id,
        status="queued",
        created_at=created_at,
        message="Job enfileirado para processamento"
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Consultar status de qualquer tipo de job (main, split, page, merge)"""
    redis_client = get_redis_client()

    # Get job status from Redis
    status_data = redis_client.get_job_status(job_id)

    if not status_data:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado")

    # Parse timestamps
    started_at = None
    completed_at = None

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
        "created_at": datetime.utcnow(),  # TODO: Store created_at in Redis
        "started_at": started_at,
        "completed_at": completed_at,
        "error": status_data.get("error"),
    }

    # Add parent_job_id for child jobs (split, page, merge)
    if "parent_job_id" in status_data:
        response_data["parent_job_id"] = status_data["parent_job_id"]

    # Add page_number for page jobs
    if "page_number" in status_data:
        response_data["page_number"] = status_data["page_number"]

    # Add child jobs info for main jobs
    if job_type == "main":
        total_pages = redis_client.get_job_pages_total(job_id)

        if total_pages:
            response_data["total_pages"] = total_pages
            response_data["pages_completed"] = redis_client.count_completed_page_jobs(job_id)
            response_data["pages_failed"] = redis_client.count_failed_page_jobs(job_id)

        # Add child jobs information
        if "child_job_ids" in status_data and status_data["child_job_ids"]:
            child_jobs_data = status_data["child_job_ids"]
            response_data["child_jobs"] = ChildJobs(
                split_job_id=child_jobs_data.get("split_job_id"),
                page_job_ids=child_jobs_data.get("page_job_ids", []),
                merge_job_id=child_jobs_data.get("merge_job_id"),
            )

    return JobStatusResponse(**response_data)


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
async def get_job_result(job_id: str):
    """Recuperar resultado de qualquer tipo de job (main ou page individual)"""
    redis_client = get_redis_client()

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

    # Get job type
    job_type = status_data.get("type", "main")

    # Get result from Redis
    result_data = redis_client.get_job_result(job_id)

    if not result_data:
        raise HTTPException(status_code=404, detail="Resultado não encontrado ou expirado")

    completed_at = None
    if "completed_at" in status_data and status_data["completed_at"]:
        completed_at = datetime.fromisoformat(status_data["completed_at"])

    # Build response
    response_data = {
        "job_id": job_id,
        "type": job_type,
        "status": "completed",
        "result": result_data,
        "completed_at": completed_at or datetime.utcnow(),
    }

    # Add page info for page jobs
    if job_type == "page":
        response_data["page_number"] = status_data.get("page_number")
        response_data["parent_job_id"] = status_data.get("parent_job_id")

    return JobResultResponse(**response_data)


@router.get("/jobs/{job_id}/pages", response_model=JobPagesResponse)
async def get_job_pages(job_id: str):
    """Obter progresso detalhado por página com job_id de cada página (para PDFs)"""
    redis_client = get_redis_client()

    # Check if job has pages
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
async def get_page_status_by_number(job_id: str, page_number: int):
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

    # Buscar page_job_id pelo número da página
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
async def get_page_result_by_number(job_id: str, page_number: int):
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

    # Buscar page_job_id pelo número da página
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


@router.get("/jobs", summary="Listar todos os jobs")
async def list_jobs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
):
    """
    Lista todos os jobs criados

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
        # Pattern: job:*:status
        all_keys = redis_client.client.keys("job:*:status")

        # Extract job IDs
        job_ids = []
        for key in all_keys:
            # Key format: job:{job_id}:status
            parts = key.split(":")
            if len(parts) >= 3:
                job_id = parts[1]
                job_ids.append(job_id)

        # Get status for each job
        jobs_list = []
        for job_id in job_ids:
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


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint"""
    redis_client = get_redis_client()

    # Check Redis
    redis_ok = redis_client.ping()

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
    if redis_ok and worker_count > 0:
        status = "healthy"
    elif redis_ok:
        status = "degraded"
    else:
        status = "unhealthy"

    response = HealthCheckResponse(
        status=status,
        redis=redis_ok,
        workers={
            "active": worker_count,
            "available": worker_count,
        },
        timestamp=datetime.utcnow(),
    )

    # Return 503 if unhealthy
    if status == "unhealthy":
        raise HTTPException(status_code=503, detail=response.dict())

    return response
