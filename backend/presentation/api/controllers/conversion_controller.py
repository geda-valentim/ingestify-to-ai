"""
Conversion Controller - Clean Architecture Example

Controller MAGRO que apenas:
1. Valida input (Pydantic)
2. Converte para DTO
3. Chama Use Case
4. Converte resposta para Pydantic
5. Retorna JSON

Toda lógica de negócio está nos Use Cases!
"""
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional
from pathlib import Path

from shared.models import User
from shared.config import get_settings

# Application Layer
from application.use_cases.convert_document import (
    ConvertDocumentUseCase,
    ConvertDocumentError
)
from application.use_cases.get_job_status import (
    GetJobStatusUseCase,
    JobNotFoundError,
    UnauthorizedError as JobUnauthorizedError
)
from application.use_cases.get_job_result import (
    GetJobResultUseCase,
    JobNotCompletedError,
    ResultNotFoundError
)
from application.dto.convert_request_dto import ConvertRequestDTO

# Presentation Layer
from presentation.api.dependencies import (
    get_convert_document_use_case,
    get_get_job_status_use_case,
    get_get_job_result_use_case,
    get_current_user
)
from presentation.schemas.requests import ConvertRequest
from presentation.schemas.responses import (
    JobCreatedResponse,
    JobStatusResponse,
    JobResultResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2", tags=["Conversion (Clean Architecture)"])
settings = get_settings()


@router.post("/convert", response_model=JobCreatedResponse, summary="Convert document (Clean Architecture)")
async def convert_document(
    # Input validation (Pydantic)
    file: UploadFile = File(..., description="File to convert"),
    name: Optional[str] = Form(None, description="Optional job name"),
    # Dependencies (injected)
    current_user: User = Depends(get_current_user),
    use_case: ConvertDocumentUseCase = Depends(get_convert_document_use_case)
):
    """
    **Clean Architecture Example**: Converte documento para Markdown

    Este endpoint demonstra Clean Architecture:
    - Controller é MAGRO (apenas adaptação)
    - Lógica de negócio está no Use Case
    - Facilmente testável (mock do Use Case)

    ## Fluxo:
    1. Valida input (Pydantic)
    2. Salva arquivo temporário
    3. Converte para DTO
    4. Executa Use Case
    5. Retorna response

    ## Benefícios:
    - Controller sem lógica de negócio
    - Use Case reutilizável (CLI, Workers, etc.)
    - Testável sem FastAPI
    """
    logger.info(f"[Clean Arch] Converting document: {file.filename}, user={current_user.username}")

    # 1. Read and validate file
    file_contents = await file.read()
    file_size_bytes = len(file_contents)
    file_size_mb = file_size_bytes / (1024 * 1024)

    if file_size_mb > settings.max_file_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size_mb:.2f}MB. Max: {settings.max_file_size_mb}MB"
        )

    # 2. Save temporary file
    temp_dir = Path(settings.temp_storage_path) / "uploads_v2"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / f"{current_user.id}_{file.filename}"

    with open(temp_file_path, "wb") as f:
        f.write(file_contents)

    # 3. Convert to DTO (Application layer)
    dto = ConvertRequestDTO(
        user_id=current_user.id,
        source_type="file",
        source=str(temp_file_path),
        filename=file.filename,
        file_size_bytes=file_size_bytes,
        mime_type=file.content_type or "application/octet-stream",
        name=name,
        options={},
    )

    # 4. Execute Use Case (where business logic lives!)
    try:
        response_dto = await use_case.execute(dto)
    except ConvertDocumentError as e:
        logger.error(f"Conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    # 5. Convert DTO to Pydantic response (Presentation layer)
    return JobCreatedResponse(
        job_id=response_dto.job_id,
        status=response_dto.status,
        created_at=response_dto.created_at,
        message=response_dto.message
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, summary="Get job status (Clean Architecture)")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    use_case: GetJobStatusUseCase = Depends(get_get_job_status_use_case)
):
    """
    **Clean Architecture**: Retorna status do job

    Controller simplesmente:
    - Extrai job_id da URL
    - Chama Use Case
    - Retorna response

    Toda lógica (ownership, pages, progress) está no Use Case!
    """
    logger.info(f"[Clean Arch] Getting status for job {job_id}, user={current_user.username}")

    try:
        # Execute Use Case
        response_dto = await use_case.execute(job_id=job_id, user_id=current_user.id)

        # Convert DTO to Pydantic response
        return JobStatusResponse(
            job_id=response_dto.job_id,
            type=response_dto.type,
            status=response_dto.status,
            progress=response_dto.progress,
            created_at=response_dto.created_at,
            started_at=response_dto.started_at,
            completed_at=response_dto.completed_at,
            error=response_dto.error,
            name=response_dto.name,
            total_pages=response_dto.total_pages,
            pages_completed=response_dto.pages_completed,
            pages_failed=response_dto.pages_failed,
        )

    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except JobUnauthorizedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse, summary="Get job result (Clean Architecture)")
async def get_job_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
    use_case: GetJobResultUseCase = Depends(get_get_job_result_use_case)
):
    """
    **Clean Architecture**: Retorna resultado convertido

    Controller delega para Use Case que:
    - Verifica ownership
    - Verifica se job completou
    - Busca resultado do storage
    - Retorna markdown
    """
    logger.info(f"[Clean Arch] Getting result for job {job_id}, user={current_user.username}")

    try:
        # Execute Use Case
        response_dto = await use_case.execute(job_id=job_id, user_id=current_user.id)

        # Convert DTO to Pydantic response
        return JobResultResponse(
            job_id=response_dto.job_id,
            type=response_dto.type,
            status=response_dto.status,
            result=response_dto.result,
            completed_at=response_dto.completed_at,
        )

    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except JobUnauthorizedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except JobNotCompletedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ResultNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
