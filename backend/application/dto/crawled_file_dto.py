"""
Crawled File DTO - Data Transfer Object for crawled files

DTOs para representar arquivos individuais baixados durante crawling.
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import datetime


class CrawledFileDTO(BaseModel):
    """
    DTO para arquivo crawleado individual.

    Representa um arquivo (PDF, imagem, CSS, JS, etc) baixado durante execução.
    """
    file_id: str = Field(..., description="ID do arquivo")
    execution_id: str = Field(..., description="ID da execução")
    url: str = Field(..., description="URL original do arquivo")
    filename: str = Field(..., description="Nome do arquivo")

    # Metadata
    file_type: Optional[str] = Field(default=None, description="Tipo (pdf, jpg, css, js, etc)")
    mime_type: Optional[str] = Field(default=None, description="MIME type (application/pdf, etc)")
    size_bytes: int = Field(..., description="Tamanho em bytes")
    size_mb: float = Field(..., description="Tamanho em MB")

    # MinIO
    minio_path: Optional[str] = Field(default=None, description="Caminho no MinIO")
    minio_bucket: str = Field(..., description="Bucket do MinIO")
    public_url: Optional[str] = Field(default=None, description="URL pública (pre-signed)")

    # Status
    status: str = Field(
        ...,
        description="Status: pending, downloading, completed, failed, skipped"
    )
    error_message: Optional[str] = Field(default=None, description="Erro se failed")

    # Timestamps
    downloaded_at: Optional[datetime] = Field(default=None, description="Data do download")
    created_at: datetime = Field(..., description="Data de criação do registro")

    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "file-abc123",
                "execution_id": "exec-789",
                "url": "https://example.com/docs/manual.pdf",
                "filename": "manual.pdf",
                "file_type": "pdf",
                "mime_type": "application/pdf",
                "size_bytes": 1048576,
                "size_mb": 1.0,
                "minio_path": "crawled/exec-789/files/manual.pdf",
                "minio_bucket": "ingestify-crawled",
                "public_url": "https://minio.example.com/presigned-url",
                "status": "completed",
                "error_message": None,
                "downloaded_at": "2025-01-13T02:03:15Z",
                "created_at": "2025-01-13T02:03:10Z"
            }
        }


class CrawledFileListDTO(BaseModel):
    """DTO resumido para listagem de arquivos"""
    file_id: str
    url: str
    filename: str
    file_type: Optional[str]
    size_mb: float
    status: str
    downloaded_at: Optional[datetime]


class CrawledFilesResponseDTO(BaseModel):
    """
    Resposta contendo lista de arquivos crawleados.

    Usado por GET /api/crawler/executions/{execution_id}/files
    """
    execution_id: str = Field(..., description="ID da execução")
    total_files: int = Field(..., description="Total de arquivos")
    files: list[CrawledFileListDTO] = Field(..., description="Lista de arquivos")

    # Filtros aplicados
    filter_type: Optional[str] = Field(default=None, description="Filtro por tipo")
    filter_status: Optional[str] = Field(default=None, description="Filtro por status")

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec-789",
                "total_files": 12,
                "files": [
                    {
                        "file_id": "file-abc123",
                        "url": "https://example.com/docs/manual.pdf",
                        "filename": "manual.pdf",
                        "file_type": "pdf",
                        "size_mb": 1.0,
                        "status": "completed",
                        "downloaded_at": "2025-01-13T02:03:15Z"
                    }
                ],
                "filter_type": None,
                "filter_status": None
            }
        }


class FileDownloadStatsDTO(BaseModel):
    """
    Estatísticas de download de arquivos.

    Métricas de performance de download.
    """
    total_files: int = Field(..., description="Total de arquivos")
    completed: int = Field(..., description="Completos")
    pending: int = Field(..., description="Pendentes")
    failed: int = Field(..., description="Falhados")
    skipped: int = Field(..., description="Pulados (duplicatas)")

    total_size_bytes: int = Field(..., description="Tamanho total")
    total_size_mb: float = Field(..., description="Tamanho em MB")

    # Breakdown por tipo
    by_type: dict[str, int] = Field(
        ...,
        description="Contagem por tipo (pdf: 5, jpg: 7, ...)"
    )

    # Performance
    avg_file_size_mb: float = Field(..., description="Tamanho médio de arquivo")
    avg_download_time_seconds: Optional[float] = Field(
        default=None,
        description="Tempo médio de download"
    )
    avg_download_speed_mbps: Optional[float] = Field(
        default=None,
        description="Velocidade média (MB/s)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_files": 15,
                "completed": 12,
                "pending": 1,
                "failed": 1,
                "skipped": 1,
                "total_size_bytes": 5242880,
                "total_size_mb": 5.0,
                "by_type": {
                    "pdf": 8,
                    "jpg": 4
                },
                "avg_file_size_mb": 0.42,
                "avg_download_time_seconds": 2.5,
                "avg_download_speed_mbps": 0.17
            }
        }
