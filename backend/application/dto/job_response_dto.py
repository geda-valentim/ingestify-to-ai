"""Job Response DTOs"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class JobResponseDTO:
    """DTO para resposta de criação de job"""
    job_id: str
    status: str
    created_at: datetime
    message: str


@dataclass
class PageInfoDTO:
    """DTO para informações de página"""
    page_number: int
    job_id: str
    status: str
    url: str


@dataclass
class JobStatusResponseDTO:
    """DTO para resposta de status de job"""
    job_id: str
    type: str
    status: str
    progress: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    name: Optional[str] = None

    # Multi-page PDF specific
    total_pages: Optional[int] = None
    pages_completed: int = 0
    pages_failed: int = 0
    pages: List[PageInfoDTO] = None

    # Hierarchical
    parent_job_id: Optional[str] = None
    page_number: Optional[int] = None  # For PAGE jobs
    child_jobs: Optional[Dict[str, Any]] = None


@dataclass
class JobResultResponseDTO:
    """DTO para resposta de resultado de job"""
    job_id: str
    type: str
    status: str
    result: Dict[str, Any]  # {markdown, metadata}
    completed_at: datetime

    # For PAGE jobs
    page_number: Optional[int] = None
    parent_job_id: Optional[str] = None
