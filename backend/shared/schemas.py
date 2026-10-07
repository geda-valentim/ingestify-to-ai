from pydantic import model_validator
from typing import Annotated
from shared.vision_capabilities import VisionTask, VISION_TASKS, task_catalog
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from typing import Optional, Literal, List, Any, Dict
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
    PROCESSING = "processing"
    PARTIAL = "partial" # Resultado preservado com lacunas
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


class ProjectRef(BaseModel):
    """A project as other resources point at it."""
    id: str
    name: str


class FolderRef(BaseModel):
    id: str
    name: str


class UploadProjectInfo(BaseModel):
    """Where an upload went (spec 0004): the project and how it was chosen."""
    id: str
    name: str
    created: bool = Field(..., description="true when this upload created the project (get-or-add)")
    source: Literal["request", "api_key", "fallback"] = Field(
        ..., description="request: named in the request; api_key: the key's bound project; "
                         "fallback: UPLOAD_FALLBACK_PROJECT (emergency valve)")


class UploadFolderInfo(BaseModel):
    id: str
    name: str
    created: bool


class JobCreatedResponse(BaseModel):
    job_id: UUID
    status: Literal["queued"]
    created_at: datetime
    message: str
    project: Optional[UploadProjectInfo] = None
    folder: Optional[UploadFolderInfo] = None


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

    # O arquivo original ainda existe (MinIO ou cópia local)? false depois de
    # purge_source ou de DELETE /jobs/{job_id}/source, e para jobs filhos
    source_available: bool = False

    # Onde o job está (spec 0004). Jobs filhos herdam do job MAIN.
    project: Optional[ProjectRef] = None
    folder: Optional[FolderRef] = None

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
    phase: Optional[Literal["transcribing", "aligning", "diarizing", "saving"]] = None

    # Só com roteamento (spec 0003): onde o job roda e por que ainda espera.
    # Nada de orçamento ou de outros usuários; null sem rota.
    kind: Optional[str] = None
    configuration: Optional[dict] = None
    image_analysis: Optional[dict] = None
    datalake: Optional[dict] = None
    engine: Optional[JobEngine] = None
    queue_reason: Optional[Literal["in_queue", "starting"]] = None


class SourceDeletedResponse(BaseModel):
    """Resposta de DELETE /jobs/{job_id}/source"""
    job_id: str
    source_deleted: bool


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


class TranscriptSpeaker(BaseModel):
    id: str
    label: str


class DiarizationTurn(BaseModel):
    start: float
    end: float
    speaker_id: str


class DiarizationMetadata(BaseModel):
    status: Literal['completed', 'disabled']
    speaker_count: Optional[int] = None
    engine: Optional[str] = None
    model: Optional[str] = None
    revision: Optional[Any] = None
    turns: List[DiarizationTurn] = []
    generation: Optional[int] = None
    provenance: Optional[Dict[str, Any]] = None
    analysis_status: Optional[str] = None
    reason_code: Optional[str] = None


class AlignmentMetadata(BaseModel):
    status: Literal['completed', 'unavailable']
    model: Optional[str] = None
    revision: Optional[str] = None
    device: Optional[str] = None
    reason: Optional[str] = None


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
    schema_version: Optional[int] = None
    speakers: Optional[List[TranscriptSpeaker]] = None
    diarization: Optional[DiarizationMetadata] = None
    alignment: Optional[AlignmentMetadata] = None
    provenance: Optional[Dict[str, Any]] = None


class ConversionResult(BaseModel):
    markdown: str
    metadata: DocumentMetadata
    image: Optional["ImageJobResult | ImageFullAnalysisResult | ImageFullV2Result | FaceAnalysisResult"] = None


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
    # Spec 0019: only read while the installation has no root user yet, and only
    # required when ROOT_SETUP_TOKEN is configured (always, in production)
    setup_token: Optional[str] = Field(None, max_length=256, description="Installation setup token; only read when creating the root user")


class SetupStatus(BaseModel):
    """Whether the installation still needs its root user (spec 0019)"""
    root_exists: bool
    # Brand-new installation (no users): the next registration becomes root
    root_pending: bool
    # Whether that root registration needs ROOT_SETUP_TOKEN
    setup_token_required: bool


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
    # The installation's single root user (spec 0019)
    is_root: bool = False
    # Flat list: the 0009 engine permissions plus the platform/IAM ones (spec 0014 CA12)
    permissions: list[str] = []
    engine_access_enabled: bool = False
    # Emergency access (users.is_admin / ADMIN_USER_IDS), never a binding (spec 0014 CA8)
    bootstrap: bool = False
    # Managed platform roles held through active bindings (empty unless IAM_MODE=enforce)
    platform_roles: list[str] = []

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
    project: Optional[str] = Field(
        None, description="Projeto vinculado, por nome (criado se não existir). Exclusivo com project_id."
    )
    project_id: Optional[str] = Field(None, description="Projeto vinculado, por ID. Exclusivo com project.")


class APIKeyProjectUpdate(BaseModel):
    """PATCH /api-keys/{key_id}: bind the key to a project, or unbind it with null."""
    project_id: Optional[str] = Field(
        ..., description="Projeto para onde vão os uploads desta key que não dizem o projeto; null desvincula."
    )


class APIKeyResponse(BaseModel):
    """Schema for API key response (after creation)"""
    id: UUID
    name: str
    api_key: str  # Only returned once during creation
    expires_at: Optional[datetime] = None
    created_at: datetime
    project: Optional[ProjectRef] = None

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
    project: Optional[ProjectRef] = None

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
    project: Optional[str] = Field(
        None, description="Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto."
    )
    project_id: Optional[str] = Field(None, description="ID de um projeto existente (alternativa a `project`).")
    folder: Optional[str] = Field(None, description="Nome da pasta no projeto (opcional, get-or-add, sem '/').")
    folder_id: Optional[str] = Field(None, description="ID de uma pasta existente do projeto.")
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
    project: Optional[str] = Field(
        None, description="Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto."
    )
    project_id: Optional[str] = Field(None, description="ID de um projeto existente (alternativa a `project`).")
    folder: Optional[str] = Field(None, description="Nome da pasta no projeto (opcional, get-or-add, sem '/').")
    folder_id: Optional[str] = Field(None, description="ID de uma pasta existente do projeto.")


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
    project: Optional[UploadProjectInfo] = None
    folder: Optional[UploadFolderInfo] = None


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
    max_image_size_mb: int = 10
    caption_tasks: List[str] = list(VISION_CAPTION_TASKS)
    default_caption_task: str = DEFAULT_VISION_CAPTION_TASK
    tasks: List["VisionTaskInfo"] = Field(default_factory=lambda: [VisionTaskInfo(**item) for item in task_catalog()])
    generation_schema: dict = Field(default_factory=lambda: VisionGenerationOptions.model_json_schema())
    generation_defaults: dict = Field(default_factory=lambda: _vision_generation_defaults())
    analysis_modes: list[str] = ["single", "full"]
    full_profiles: List[dict] = Field(default_factory=list)
    faces: Optional[dict] = None
    full_profile: str = "image-full-v1"
    full_limits: dict = {"max_queries": 3, "max_regions": 4, "max_calls": 32, "deadline_seconds": 900}


class ImageJobResult(BaseModel):
    """Persisted vision output, including the operation selected at upload."""

    operation: Literal["describe", "ocr", "analyze"]
    task: str
    task_label: Optional[str] = None
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None
    width: int
    height: int
    description: Optional[str] = None
    text: Optional[str] = None
    lines: List[OcrLine] = []
    model: VisionModelInfo
    duration_ms: int
    output: Optional[dict | str] = None
    regions: List["ImageRegion"] = []
    request: Optional["ImageAnalyzeOptions"] = None


class VisionTaskInfo(BaseModel):
    task: VisionTask
    label: str
    output: Literal["text", "ocr", "boxes", "polygons", "mixed"]
    input: Literal["none", "text", "region"]


class VisionGenerationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_new_tokens: Optional[int] = Field(None, ge=1, le=1024, description="Limite de tokens gerados (contexto do checkpoint integrado: 1024); omitido usa a configuração do worker.")
    num_beams: Optional[int] = Field(None, ge=1, le=8, description="Número de candidatos na busca; omitido usa a configuração do worker.")
    do_sample: bool = Field(False, description="Amostrar o próximo token em vez de usar busca determinística.")
    temperature: float = Field(1.0, gt=0, le=2, description="Variação da amostragem; utilizada quando do_sample=true.")
    top_p: float = Field(1.0, gt=0, le=1, description="Fração acumulada de probabilidade na amostragem.")
    top_k: int = Field(50, ge=0, le=100, description="Quantidade de candidatos na amostragem; zero não limita.")
    repetition_penalty: float = Field(1.0, ge=0.5, le=3, description="Penalidade de tokens repetidos.")
    length_penalty: float = Field(1.0, ge=-2, le=2, description="Preferência por sequências longas na busca por beams.")
    no_repeat_ngram_size: int = Field(0, ge=0, le=20, description="Impedir repetição de sequências deste tamanho; zero desativa.")
    early_stopping: bool | Literal["never"] = Field(False, description="Critério de parada da busca por beams.")

    @model_validator(mode="after")
    def validate_decoding_mode(self):
        if not self.do_sample and (self.temperature != 1 or self.top_p != 1 or self.top_k != 50):
            raise ValueError("temperature/top_p/top_k diferentes do padrão exigem do_sample=true")
        if self.num_beams == 1 and (self.length_penalty != 1 or self.early_stopping is not False):
            raise ValueError("length_penalty/early_stopping personalizados exigem num_beams > 1")
        return self


class ImageAnalyzeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: VisionTask = Field(DEFAULT_VISION_CAPTION_TASK, json_schema_extra={"x-task-catalog": task_catalog()})
    text_input: Optional[str] = Field(None, min_length=1, max_length=2000, description="Frase/descrição/objetos nas tarefas que recebem texto.")
    region: Optional[List[float]] = Field(None, min_length=4, max_length=4, description="Região normalizada [x_min,y_min,x_max,y_max], valores entre 0 e 1.")
    generation: VisionGenerationOptions = Field(default_factory=VisionGenerationOptions)

    @model_validator(mode="after")
    def validate_task_input(self):
        input_kind = VISION_TASKS[self.task][2]
        if self.text_input is not None:
            self.text_input = self.text_input.strip()
        if input_kind == "text" and not self.text_input:
            raise ValueError(f"{self.task} exige text_input")
        if input_kind != "text" and self.text_input is not None:
            raise ValueError(f"{self.task} não recebe text_input")
        if input_kind == "region" and self.region is None:
            raise ValueError(f"{self.task} exige region")
        if input_kind != "region" and self.region is not None:
            raise ValueError(f"{self.task} não recebe region")
        if self.region is not None:
            import math
            x1, y1, x2, y2 = self.region
            if not all(math.isfinite(v) and 0 <= v <= 1 for v in self.region) or x1 >= x2 or y1 >= y2:
                raise ValueError("region exige 0 <= x_min < x_max <= 1 e 0 <= y_min < y_max <= 1")
        return self


class ImageAnalyzeRequest(ImageOcrRequest, ImageAnalyzeOptions):
    mode: Literal["single"] = "single"
    wait: bool = Field(False, description="false cria um job e retorna 202; true espera pelo resultado (sujeito ao timeout de visão).")


class ImageRegion(BaseModel):
    label: str = ""
    score: Optional[float] = None
    bbox: Optional[List[float]] = None
    quad_box: Optional[List[float]] = None
    polygons: List[List[float]] = []


class ImageAnalyzeResponse(_ImageEchoResponse):
    task: VisionTask
    text: str
    output: dict | str
    regions: List[ImageRegion]
    request: ImageAnalyzeOptions


def _vision_generation_defaults():
    from shared.config import get_settings
    settings = get_settings()
    return VisionGenerationOptions(max_new_tokens=settings.vision_max_new_tokens,
                                   num_beams=settings.vision_num_beams).model_dump()



from shared.face_analysis import FaceRequestOptions, FullFaceOptions, FaceAnalysisResult, FaceStepResult, FaceModelInfo, FacialBlock


class FaceAnalyzeRequest(ImageOcrRequest):
    model_config = ConfigDict(extra='forbid')
    face_options: FaceRequestOptions = Field(default_factory=FaceRequestOptions)
    wait: bool = False
    datalake: Optional['Destination'] = None


class FaceAnalyzeResponse(BaseModel):
    job_id: str
    status: str
    markdown: str
    image: FaceAnalysisResult


class ImageFullOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Literal['image-full-v1', 'image-full-v2'] = 'image-full-v1'
    faces: Optional[FullFaceOptions] = None
    queries: Optional[List[str]] = Field(None, min_length=1, max_length=3)
    regions: Optional[List[List[float]]] = Field(None, min_length=1, max_length=4)
    generation: VisionGenerationOptions = Field(default_factory=VisionGenerationOptions)
    deadline_seconds: int = Field(900, ge=1, le=900)

    @model_validator(mode="after")
    def validate_inputs(self):
        if self.profile == 'image-full-v1' and self.faces is not None:
            raise ValueError('faces exige profile=image-full-v2')
        if self.profile == 'image-full-v2' and self.faces is None:
            self.faces = FullFaceOptions()
        if self.queries is not None:
            self.queries = [q.strip() for q in self.queries]
            if any(not q or len(q) > 2000 for q in self.queries) or len('. '.join(self.queries)) > 2000:
                raise ValueError('queries devem ser não vazias e totalizar no máximo 2000 caracteres')
        for box in self.regions or []:
            ImageAnalyzeOptions(task='<REGION_TO_CATEGORY>', region=box)
        return self


class ImageFullAnalyzeRequest(ImageOcrRequest):
    model_config = ConfigDict(extra="forbid")
    mode: Literal['full']
    full_options: ImageFullOptions = Field(default_factory=ImageFullOptions)
    wait: bool = False
    datalake: Optional['Destination'] = None


class ImageFullStepResult(BaseModel):
    step_id: str
    task: VisionTask
    input: dict = Field(default_factory=dict)
    status: Literal['pending', 'running', 'succeeded', 'failed', 'skipped', 'not_applicable']
    reason_code: Optional[str] = None
    text: str = ''
    output: dict | str = ''
    regions: List[ImageRegion] = Field(default_factory=list)
    lines: List[OcrLine] = Field(default_factory=list)
    duration_ms: int = 0
    truncated: bool = False
    generation_metadata: dict = Field(default_factory=dict)
    attempts: int = 0


class ImageFullAnalysisResult(BaseModel):
    operation: Literal['full_analysis']
    schema_version: Literal['image-full-result-v1'] = 'image-full-result-v1'
    profile: Literal['image-full-v1'] = 'image-full-v1'
    analysis_status: Literal['completed', 'partial', 'failed', 'cancelled']
    task: str = 'full'
    task_label: str = 'Full Analysis'
    image_base64: Optional[str] = None
    image_mime_type: str = 'image/png'
    width: int
    height: int
    model: VisionModelInfo
    duration_ms: int
    description: str = ''
    text: str = ''
    lines: List[OcrLine] = Field(default_factory=list)
    regions: List[ImageRegion] = Field(default_factory=list)
    request: Optional[dict] = None
    coverage: dict
    resolved_inputs: dict = Field(default_factory=dict)
    results: List[ImageFullStepResult]
    calls_started: int = 0
    reason_code: Optional[str] = None
    source_sha256: str = ''
    frame_policy: str = 'first_frame'


class FlorenceV2StepResult(ImageFullStepResult):
    kind: Literal['florence'] = 'florence'


class ImageFullV2Result(ImageFullAnalysisResult):
    schema_version: Literal['image-full-result-v2'] = 'image-full-result-v2'
    profile: Literal['image-full-v2'] = 'image-full-v2'
    models: List[FaceModelInfo | dict]
    faces: FacialBlock
    results: List[Annotated[FlorenceV2StepResult | FaceStepResult, Field(discriminator='kind')]]
    calls_by_provider: dict[str, int] = Field(default_factory=dict)


class ImageFullQueuedResponse(JobCreatedResponse):
    status: JobStatus
    poll_url: str
    result_url: str


class ImageFullAnalyzeResponse(BaseModel):
    job_id: str
    status: str
    markdown: str
    image: ImageFullAnalysisResult | ImageFullV2Result


from shared.datalake.schemas import Destination
ImageFullAnalyzeRequest.model_rebuild()
FaceAnalyzeRequest.model_rebuild()

ConversionResult.model_rebuild()
JobResultResponse.model_rebuild()
VisionCapabilitiesResponse.model_rebuild()
