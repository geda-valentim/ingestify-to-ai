"""
Crawler Execution DTO - Data Transfer Object for execution views

DTOs para representar execuções de crawler.
Uma execução = um Job com job_type=DOWNLOAD e parent_job_id=crawler_job_id.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CrawlerExecutionDTO(BaseModel):
    """
    DTO para uma execução de crawler.

    Representa uma execução individual (manual ou agendada).
    Mapeia para um Job entity com job_type=DOWNLOAD.
    """
    execution_id: str = Field(..., description="ID da execução (Job.id)")
    crawler_job_id: str = Field(..., description="ID do crawler job pai")
    user_id: str = Field(..., description="ID do usuário")

    # Status
    status: str = Field(
        ...,
        description="Status: pending, processing, completed, failed, cancelled"
    )
    progress: int = Field(..., ge=0, le=100, description="Progresso (0-100%)")
    error_message: Optional[str] = Field(default=None, description="Mensagem de erro se falhou")

    # Estatísticas
    pages_crawled: int = Field(default=0, description="Páginas crawleadas com sucesso")
    pages_failed: int = Field(default=0, description="Páginas que falharam")
    files_downloaded: int = Field(default=0, description="Arquivos baixados")
    files_failed: int = Field(default=0, description="Arquivos que falharam")
    total_size_bytes: int = Field(default=0, description="Tamanho total de arquivos baixados")

    # Tempo
    started_at: Optional[datetime] = Field(default=None, description="Início da execução")
    completed_at: Optional[datetime] = Field(default=None, description="Fim da execução")
    duration_seconds: Optional[int] = Field(default=None, description="Duração em segundos")

    # MinIO paths
    minio_path: Optional[str] = Field(
        default=None,
        description="Caminho base no MinIO (crawled/{execution_id}/)"
    )

    # Timestamps
    created_at: datetime = Field(..., description="Data de criação")
    updated_at: datetime = Field(..., description="Data de atualização")

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec-789",
                "crawler_job_id": "job-123",
                "user_id": "user-456",
                "status": "completed",
                "progress": 100,
                "error_message": None,
                "pages_crawled": 45,
                "pages_failed": 2,
                "files_downloaded": 12,
                "files_failed": 1,
                "total_size_bytes": 5242880,
                "started_at": "2025-01-13T02:00:00Z",
                "completed_at": "2025-01-13T02:05:30Z",
                "duration_seconds": 330,
                "minio_path": "crawled/exec-789/",
                "created_at": "2025-01-13T01:59:55Z",
                "updated_at": "2025-01-13T02:05:30Z"
            }
        }


class CrawlerExecutionListDTO(BaseModel):
    """DTO resumido para listagem de execuções"""
    execution_id: str
    crawler_job_id: str
    status: str
    progress: int
    pages_crawled: int
    files_downloaded: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_at: datetime


class ExecutionStatsDTO(BaseModel):
    """
    Estatísticas detalhadas de uma execução.

    Informações agregadas sobre páginas e arquivos crawleados.
    """
    execution_id: str = Field(..., description="ID da execução")

    # Páginas
    total_pages: int = Field(..., description="Total de páginas encontradas")
    pages_crawled: int = Field(..., description="Páginas crawleadas")
    pages_pending: int = Field(..., description="Páginas pendentes")
    pages_failed: int = Field(..., description="Páginas que falharam")

    # Arquivos
    total_files: int = Field(..., description="Total de arquivos encontrados")
    files_downloaded: int = Field(..., description="Arquivos baixados")
    files_pending: int = Field(..., description="Arquivos pendentes")
    files_failed: int = Field(..., description="Arquivos que falharam")
    files_skipped: int = Field(..., description="Arquivos pulados (duplicatas)")

    # Tamanho
    total_size_bytes: int = Field(..., description="Tamanho total baixado")
    total_size_mb: float = Field(..., description="Tamanho total em MB")

    # Arquivos por tipo
    files_by_type: dict[str, int] = Field(
        ...,
        description="Contagem por tipo de arquivo (pdf: 5, jpg: 10, ...)"
    )

    # Performance
    avg_download_speed_mbps: Optional[float] = Field(
        default=None,
        description="Velocidade média de download (MB/s)"
    )
    duration_seconds: Optional[int] = Field(
        default=None,
        description="Duração da execução"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec-789",
                "total_pages": 50,
                "pages_crawled": 45,
                "pages_pending": 3,
                "pages_failed": 2,
                "total_files": 15,
                "files_downloaded": 12,
                "files_pending": 1,
                "files_failed": 1,
                "files_skipped": 1,
                "total_size_bytes": 5242880,
                "total_size_mb": 5.0,
                "files_by_type": {
                    "pdf": 8,
                    "jpg": 4
                },
                "avg_download_speed_mbps": 0.25,
                "duration_seconds": 330
            }
        }


class ExecutionHistoryDTO(BaseModel):
    """
    Histórico de execuções de um crawler job.

    Lista paginada de execuções passadas.
    """
    crawler_job_id: str = Field(..., description="ID do crawler job")
    total_executions: int = Field(..., description="Total de execuções")
    successful: int = Field(..., description="Execuções bem-sucedidas")
    failed: int = Field(..., description="Execuções falhadas")
    cancelled: int = Field(..., description="Execuções canceladas")

    executions: List[CrawlerExecutionListDTO] = Field(
        ...,
        description="Lista de execuções (ordenadas por data, mais recente primeiro)"
    )

    # Paginação
    page: int = Field(..., ge=1, description="Página atual")
    page_size: int = Field(..., ge=1, le=100, description="Tamanho da página")
    total_pages: int = Field(..., description="Total de páginas")

    class Config:
        json_schema_extra = {
            "example": {
                "crawler_job_id": "job-123",
                "total_executions": 25,
                "successful": 20,
                "failed": 3,
                "cancelled": 2,
                "executions": [
                    {
                        "execution_id": "exec-789",
                        "crawler_job_id": "job-123",
                        "status": "completed",
                        "progress": 100,
                        "pages_crawled": 45,
                        "files_downloaded": 12,
                        "started_at": "2025-01-13T02:00:00Z",
                        "completed_at": "2025-01-13T02:05:30Z",
                        "duration_seconds": 330,
                        "created_at": "2025-01-13T01:59:55Z"
                    }
                ],
                "page": 1,
                "page_size": 10,
                "total_pages": 3
            }
        }
