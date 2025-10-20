"""Page Response DTO"""
from dataclasses import dataclass
from typing import List


@dataclass
class PageJobInfoDTO:
    """DTO para informações de job de página"""
    page_number: int
    job_id: str
    status: str
    url: str


@dataclass
class PageResponseDTO:
    """DTO para resposta de lista de páginas"""
    job_id: str
    total_pages: int
    pages_completed: int
    pages_failed: int
    pages: List[PageJobInfoDTO]
