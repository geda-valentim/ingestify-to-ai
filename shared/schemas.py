from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional, Literal, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class JobType(str, Enum):
    """Tipos de jobs no sistema"""
    MAIN = "main"          # Job principal do usuário
    SPLIT = "split"        # Divisão de PDF em páginas
    PAGE = "page"          # Conversão de página individual
    MERGE = "merge"        # Combinação de páginas
    DOWNLOAD = "download"  # Download de fonte externa


class JobStatus(str, Enum):
    """Estados possíveis de um job"""
    QUEUED = "queued"         # Na fila
    PROCESSING = "processing" # Sendo processado
    COMPLETED = "completed"   # Concluído com sucesso
    FAILED = "failed"         # Falhou
    CANCELLED = "cancelled"   # Cancelado


class ConversionOptions(BaseModel):
    format: str = "markdown"
    include_images: bool = True
    preserve_tables: bool = True
    extract_metadata: bool = True
    chunk_size: Optional[int] = None


class ConvertRequest(BaseModel):
    source_type: Literal["file", "url", "gdrive", "dropbox"]
    source: Optional[str] = None
    name: Optional[str] = None  # Nome de identificação opcional
    options: ConversionOptions = Field(default_factory=ConversionOptions)
    callback_url: Optional[HttpUrl] = None

    @field_validator('source')
    @classmethod
    def validate_source(cls, v, info):
        if info.data.get('source_type') != 'file' and not v:
            raise ValueError('source é obrigatório para este source_type')
        return v


class JobCreatedResponse(BaseModel):
    job_id: UUID
    status: Literal["queued"]
    created_at: datetime
    message: str


class PageStatus(BaseModel):
    """Status de uma página individual"""
    page_number: int
    status: Literal["pending", "processing", "completed", "failed"]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class ChildJobs(BaseModel):
    """Jobs filhos de um job principal"""
    split_job_id: Optional[UUID] = None
    page_job_ids: Optional[List[UUID]] = None
    merge_job_id: Optional[UUID] = None


class JobStatusResponse(BaseModel):
    job_id: UUID
    type: JobType
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    # Nome de identificação
    name: Optional[str] = None

    # Para MAIN jobs
    parent_job_id: Optional[UUID] = None
    total_pages: Optional[int] = None
    pages_completed: Optional[int] = None
    pages_failed: Optional[int] = None
    child_jobs: Optional[ChildJobs] = None

    # Para PAGE jobs
    page_number: Optional[int] = None


class PageJobInfo(BaseModel):
    """Informação de um page job"""
    page_number: int
    job_id: UUID
    status: JobStatus
    url: str  # URL para consultar resultado: /jobs/{job_id}/result


class JobPagesResponse(BaseModel):
    """Detalhes de progresso por página"""
    job_id: UUID
    total_pages: int
    pages_completed: int
    pages_failed: int
    pages: List[PageJobInfo]


class DocumentMetadata(BaseModel):
    pages: Optional[int] = None
    words: Optional[int] = None
    format: str
    size_bytes: int
    title: Optional[str] = None
    author: Optional[str] = None


class ConversionResult(BaseModel):
    markdown: str
    metadata: DocumentMetadata


class JobResultResponse(BaseModel):
    job_id: UUID
    type: JobType
    status: JobStatus
    result: ConversionResult
    completed_at: datetime
    # Para PAGE jobs
    page_number: Optional[int] = None
    parent_job_id: Optional[UUID] = None


class HealthCheckResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str = "1.0.0"
    redis: bool
    workers: dict
    timestamp: datetime


class ErrorResponse(BaseModel):
    error: dict
