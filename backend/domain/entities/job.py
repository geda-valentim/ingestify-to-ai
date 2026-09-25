"""
Job Entity - Core Business Entity

Representa um job de conversão de documento.
Livre de dependências de infraestrutura.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class JobStatus(str, Enum):
    """Status possíveis de um job"""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Tipos de job na hierarquia"""
    MAIN = "main"
    SPLIT = "split"
    PAGE = "page"
    MERGE = "merge"
    DOWNLOAD = "download"
    CRAWLER = "crawler"  # Crawler agendado (STI pattern)


@dataclass
class Job:
    """
    Entidade Job - representa um trabalho de conversão

    Regras de negócio:
    - Progress deve estar entre 0 e 100
    - Status transitions devem seguir fluxo válido
    - Jobs de tipo PAGE devem ter page_number
    - Jobs MAIN podem ter child jobs
    """
    id: str
    user_id: str
    job_type: JobType
    status: JobStatus

    # File information
    filename: Optional[str] = None
    source_type: Optional[str] = None  # file, url, gdrive, dropbox
    source_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None

    # Progress tracking
    progress: int = 0
    error_message: Optional[str] = None

    # PDF-specific
    total_pages: Optional[int] = None
    pages_completed: int = 0
    pages_failed: int = 0

    # Hierarchical tracking
    parent_job_id: Optional[str] = None
    page_number: Optional[int] = None  # For PAGE jobs
    child_job_ids: List[str] = field(default_factory=list)

    # Result metadata
    char_count: Optional[int] = None
    has_result_stored: bool = False

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Display name
    name: Optional[str] = None

    def __post_init__(self):
        """Validações pós-inicialização"""
        self._validate_progress()
        self._validate_page_job()

    def _validate_progress(self):
        """Valida que progress está entre 0 e 100"""
        if not 0 <= self.progress <= 100:
            raise ValueError(f"Progress must be between 0 and 100, got {self.progress}")

    def _validate_page_job(self):
        """Valida que PAGE jobs têm page_number"""
        if self.job_type == JobType.PAGE and self.page_number is None:
            raise ValueError("PAGE jobs must have page_number")

    def update_progress(self, progress: int) -> None:
        """Atualiza progresso com validação"""
        if not 0 <= progress <= 100:
            raise ValueError(f"Progress must be between 0 and 100, got {progress}")
        self.progress = progress
        self.updated_at = datetime.utcnow()

    def mark_as_processing(self) -> None:
        """Marca job como em processamento"""
        self.status = JobStatus.PROCESSING
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_as_completed(self) -> None:
        """Marca job como completado"""
        self.status = JobStatus.COMPLETED
        self.progress = 100
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_as_failed(self, error: str) -> None:
        """Marca job como falho"""
        self.status = JobStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def add_child_job(self, child_id: str) -> None:
        """Adiciona child job ID"""
        if child_id not in self.child_job_ids:
            self.child_job_ids.append(child_id)
            self.updated_at = datetime.utcnow()

    def is_multi_page_pdf(self) -> bool:
        """Verifica se é PDF multi-página"""
        return self.total_pages is not None and self.total_pages > 1

    def can_retry(self) -> bool:
        """Verifica se job pode ser retried"""
        return self.status == JobStatus.FAILED

    def is_terminal_state(self) -> bool:
        """Verifica se job está em estado terminal"""
        return self.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
