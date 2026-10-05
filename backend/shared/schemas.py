from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
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


class JobEngine(BaseModel):
    """Onde um job roteado roda: no servidor (local) ou numa conta de nuvem (cloud)"""
    kind: Literal["local", "cloud"]


class ChildJobs(BaseModel):
    """Jobs filhos de um job principal"""
    split_job_id: Optional[UUID] = None
    page_job_ids: Optional[List[UUID]] = None
    merge_job_id: Optional[UUID] = None


class PageJobInfo(BaseModel):
    """Informação de um page job"""
    page_number: int

    # `None` while the page job does not exist yet.
    #
    # `total_pages` is published (Redis + MySQL) by the split task *before* the
    # loop that inserts the page rows one commit at a time, so between those two
    # moments the API knows how many pages there are but not their job ids. This
    # field used to be `UUID` and the routes filled the gap with fabricated ids
    # ("pending-3", "page-3"): every one of them failed Pydantic validation and
    # FastAPI turned the failure into a 500, so GET /jobs/{id} was unusable for
    # the whole split window - a window that grows with the page count.
    #
    # `Optional[str]`, not `Optional[UUID]`: job ids are opaque strings
    # everywhere else in this system (path params are `job_id: str`, `Job.id` is
    # a `String(36)` column). Parsing them into UUIDs at the serialization
    # boundary alone buys no safety and only converts data surprises into 500s.
    job_id: Optional[str] = None

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
    tags: List[str] = []

    # Para MAIN jobs
    parent_job_id: Optional[UUID] = None
    total_pages: Optional[int] = None
    pages_completed: Optional[int] = None
    pages_failed: Optional[int] = None
    pages: Optional[List[PageJobInfo]] = None  # Status detalhado de cada página
    child_jobs: Optional[ChildJobs] = None

    # Para PAGE jobs
    page_number: Optional[int] = None

    # Transcrições em andamento: quanto da mídia já foi transcrito, em segundos
    transcribed_seconds: Optional[float] = None
    media_duration: Optional[float] = None

    # Só com roteamento (spec 0003): onde o job roda e por que ainda espera.
    # Nada de orçamento ou de outros usuários; null sem rota.
    engine: Optional[JobEngine] = None
    queue_reason: Optional[Literal["in_queue", "starting"]] = None


class TranscriptSegment(BaseModel):
    """Trecho transcrito, com início e fim em segundos da mídia"""
    start: float
    end: float
    text: str


class PartialTranscriptResponse(BaseModel):
    """Texto de uma transcrição em andamento, a partir do segmento `since`"""
    job_id: UUID
    status: JobStatus
    segments: List[TranscriptSegment]
    next: int  # passe como `since` na próxima consulta para receber só o que é novo


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
    # Audio / video transcription
    language: Optional[str] = None
    duration: Optional[float] = None
    device: Optional[str] = None  # "cuda", "cpu" or "remote"
    available_formats: Optional[List[str]] = None  # use GET /jobs/{id}/result?format=...


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
    # Effective admin rule (users.is_admin OR ADMIN_USER_IDS); the API fills it in,
    # so the frontend can show admin-only screens
    is_admin: bool = False

    class Config:
        from_attributes = True

    @classmethod
    def for_user(cls, user) -> "UserResponse":
        from shared.admin import is_effective_admin

        return cls.model_validate(user).model_copy(update={"is_admin": is_effective_admin(user)})


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


# ============================================
# Vision Schemas (Florence-2)
# ============================================

# Os únicos prompts de caption que um chamador pode pedir. É um `Literal`
# fechado de propósito: o valor vai direto para o modelo, e uma string livre
# aqui seria injeção de prompt no Florence-2.
VISION_CAPTION_TASKS = (
    "<MORE_DETAILED_CAPTION>",
    "<DETAILED_CAPTION>",
    "<CAPTION>",
)


def _default_caption_task() -> str:
    """
    Default de `ImageDescribeRequest.task`, vindo de `VISION_CAPTION_TASK`.

    O `in VISION_CAPTION_TASKS` não é paranoia: o default de um campo `Literal`
    é validado quando o modelo é construído (import time). Sem essa guarda, um
    `VISION_CAPTION_TASK=<OD>` no ambiente derrubaria a API inteira no import
    com um erro de Pydantic, em vez de simplesmente ser ignorado no default.
    """
    from shared.config import get_settings

    configured = get_settings().vision_caption_task
    return configured if configured in VISION_CAPTION_TASKS else VISION_CAPTION_TASKS[0]


DEFAULT_VISION_CAPTION_TASK = _default_caption_task()


class VisionModelInfo(BaseModel):
    """Qual modelo, em qual revisão e em qual device produziu esta resposta."""

    # `model_id` colide com o namespace protegido `model_` do Pydantic v2, que
    # emitiria um warning e o carregaria para o schema OpenAPI publicado.
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    revision: str
    device: str
    dtype: str


class ImageDescribeRequest(BaseModel):
    """Corpo JSON de `POST /images/describe`."""

    image_base64: str = Field(
        ...,
        description=(
            "Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e "
            "removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF."
        ),
    )
    tags: Optional[List[str]] = Field(
        None, description="Tags do job (ex.: [\"cliente-x\", \"nf\"]). Viram minúsculas; até 20 de até 50 caracteres."
    )
    filename: Optional[str] = Field(
        None, description="Nome de identificação opcional (usado no job e no storage)."
    )
    task: Literal[
        "<MORE_DETAILED_CAPTION>",
        "<DETAILED_CAPTION>",
        "<CAPTION>",
    ] = Field(
        DEFAULT_VISION_CAPTION_TASK,
        description="Prompt de caption do Florence-2.",
    )


class ImageOcrRequest(BaseModel):
    """
    Corpo JSON de `POST /images/ocr`.

    Sem campo `task`: OCR é sempre `<OCR_WITH_REGION>`, não é escolha do
    chamador.
    """

    image_base64: str = Field(
        ...,
        description=(
            "Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e "
            "removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF."
        ),
    )
    tags: Optional[List[str]] = Field(
        None, description="Tags do job (ex.: [\"cliente-x\", \"nf\"]). Viram minúsculas; até 20 de até 50 caracteres."
    )
    filename: Optional[str] = Field(None, description="Nome de identificação opcional.")


class OcrLine(BaseModel):
    """Uma linha detectada pelo `<OCR_WITH_REGION>` do Florence-2."""

    text: str

    # Coordenadas absolutas, em pixels da imagem original, e `float` de
    # propósito: apertar para `int` na fronteira de serialização apenas
    # converteria uma surpresa de dados do modelo em um 500 (mesmo princípio
    # de `PageJobInfo.job_id`).
    quad_box: List[float] = Field(
        ...,
        description="8 valores: x1,y1,x2,y2,x3,y3,x4,y4 (pixels da imagem original).",
    )
    bbox: List[float] = Field(
        ...,
        description="4 valores derivados do quad_box: x_min,y_min,x_max,y_max.",
    )


class _ImageEchoResponse(BaseModel):
    """
    Campos comuns às respostas de visão.

    `image_base64` é a re-codificação dos bytes exatos que o chamador enviou: a
    API guarda os bytes originais em memória e nunca os passa pelo worker nem
    pelo PIL, então o echo é idêntico byte a byte por construção.
    """

    job_id: str
    status: Literal["completed"]
    image_base64: str
    image_mime_type: str
    image_bytes: int
    image_sha256: str
    width: int
    height: int
    model: VisionModelInfo
    duration_ms: int


class ImageDescribeResponse(_ImageEchoResponse):
    """Resposta de `POST /images/describe` e `/images/describe/upload`."""

    description: str
    task: str


class ImageOcrResponse(_ImageEchoResponse):
    """Resposta de `POST /images/ocr` e `/images/ocr/upload`."""

    # Uma imagem sem texto detectável é 200 com `text: ""` e `lines: []`.
    text: str
    lines: List[OcrLine]


class VisionCapabilitiesResponse(BaseModel):
    """
    Resposta de `GET /images/capabilities`.

    Respondida pelo worker de visão, não pela API: a única resposta que vale
    alguma coisa descreve o processo que realmente carrega o modelo.
    """

    model_config = ConfigDict(protected_namespaces=())

    enabled: bool
    provider: str
    model_id: str
    revision: str
    device_requested: str
    device_resolved: str
    torch_available: bool
    cuda_available: bool
    cuda_device_name: Optional[str] = None
    dependencies_installed: bool
    model_downloaded: bool
    model_loaded: bool
    trust_remote_code: bool
    reason: Optional[str] = None
