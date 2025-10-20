"""
Page Entity - Represents a single page in a PDF conversion job
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class PageStatus(str, Enum):
    """Status possíveis de uma página"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Page:
    """
    Entidade Page - representa uma página individual de um PDF

    Regras de negócio:
    - page_number deve ser >= 1
    - Cada página pertence a um job principal
    - Página pode ter seu próprio page_job_id
    """
    id: str
    job_id: str  # Main job ID
    page_number: int
    status: PageStatus

    # Page job reference (PAGE type job)
    page_job_id: Optional[str] = None

    # Result metadata
    char_count: Optional[int] = None
    has_result_stored: bool = False
    error_message: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validações pós-inicialização"""
        self._validate_page_number()

    def _validate_page_number(self):
        """Valida que page_number é >= 1"""
        if self.page_number < 1:
            raise ValueError(f"page_number must be >= 1, got {self.page_number}")

    def mark_as_processing(self, page_job_id: str) -> None:
        """Marca página como em processamento"""
        self.status = PageStatus.PROCESSING
        self.page_job_id = page_job_id
        self.updated_at = datetime.utcnow()

    def mark_as_completed(self, char_count: int) -> None:
        """Marca página como completada"""
        self.status = PageStatus.COMPLETED
        self.char_count = char_count
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_as_failed(self, error: str) -> None:
        """Marca página como falha"""
        self.status = PageStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def can_retry(self) -> bool:
        """Verifica se página pode ser retried"""
        return self.status == PageStatus.FAILED
