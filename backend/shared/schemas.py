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
    CRAWLER = "crawler"    # Crawler agendado (STI pattern)


class JobStatus(str, Enum):
    """Estados possíveis de um job"""
    PENDING = "pending"       # Pendente (usado internamente)
    QUEUED = "queued"         # Na fila
    PROCESSING = "processing" # Sendo processado
    COMPLETED = "completed"   # Concluído com sucesso
    FAILED = "failed"         # Falhou
    CANCELLED = "cancelled"   # Cancelado


class DoclingPreset(str, Enum):
    """
    Docling conversion quality/speed presets

    - FAST: Fastest conversion, text-only (no OCR, no images) - ~35s/MB
    - BALANCED: Moderate speed with image extraction - ~70-105s/MB
    - QUALITY: Full features including OCR for scanned documents - ~350s/MB
    """
    FAST = "fast"           # OCR: Off, Images: Off, Tables: On  (~35s/MB)
    BALANCED = "balanced"   # OCR: Off, Images: On, Tables: On   (~70-105s/MB)
    QUALITY = "quality"     # OCR: On, Images: On, Tables: On    (~350s/MB)


class ConversionOptions(BaseModel):
    format: str = "markdown"
    include_images: bool = True
    preserve_tables: bool = True
    extract_metadata: bool = True
    chunk_size: Optional[int] = None

    # Docling quality/speed preset (for PDF conversion only)
    docling_preset: Optional[DoclingPreset] = Field(
        default=DoclingPreset.FAST,
        description="Quality/speed preset for PDF conversion: fast (~35s/MB), balanced (~70-105s/MB), quality (~350s/MB)"
    )

    # Audio transcription options
    include_timestamps: bool = True  # Include timestamp markers in transcription
    include_word_timestamps: bool = False  # Include word-level timestamps (more detailed)
    audio_language: Optional[str] = None  # Language code (e.g., 'en', 'pt'). Auto-detect if None
    transcriber_provider: Optional[str] = None  # Override default provider: faster-whisper, openai-whisper, openai-api


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


class PageJobInfo(BaseModel):
    """Informação de um page job"""
    page_number: int
    job_id: UUID
    status: JobStatus
    url: str  # URL para consultar resultado: /jobs/{job_id}/result
    error_message: Optional[str] = None  # Error details for failed pages
    retry_count: int = 0  # Number of retry attempts (max 3)


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
    pages: Optional[List[PageJobInfo]] = None  # Status detalhado de cada página
    child_jobs: Optional[ChildJobs] = None

    # Para PAGE jobs
    page_number: Optional[int] = None


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


# ============================================
# Authentication Schemas
# ============================================

class UserCreate(BaseModel):
    """Schema for user registration"""
    email: str = Field(..., example="user@example.com")
    username: str = Field(..., min_length=3, max_length=50, example="testuser")
    password: str = Field(..., min_length=8, max_length=20, example="SecurePass123")


class UserLogin(BaseModel):
    """Schema for user login"""
    username: str = Field(..., example="testuser")  # Can be username or email
    password: str = Field(..., example="Test123")


class UserResponse(BaseModel):
    """Schema for user response"""
    id: UUID
    email: str
    username: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for token payload data"""
    user_id: Optional[str] = None


# ============================================
# API Key Schemas
# ============================================

class APIKeyCreate(BaseModel):
    """Schema for creating API key"""
    name: str = Field(..., min_length=1, max_length=100, example="Production Server")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, example=30)


class APIKeyResponse(BaseModel):
    """Schema for API key response (after creation)"""
    id: UUID
    name: str
    api_key: str  # Only returned once during creation
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyInfo(BaseModel):
    """Schema for listing API keys (without the actual key)"""
    id: UUID
    name: str
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
