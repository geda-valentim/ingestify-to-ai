"""
CrawledFile Entity

Representa um arquivo individual baixado durante uma execução de crawler.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class FileStatus(str, Enum):
    """Status possíveis de um arquivo crawleado"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CrawledFile:
    """
    Entidade CrawledFile - representa um arquivo baixado por um crawler

    Regras de negócio:
    - execution_id deve apontar para um Job válido (tipo DOWNLOAD)
    - size_bytes deve ser >= 0
    - minio_path obrigatório quando status = COMPLETED
    - error_message obrigatório quando status = FAILED
    """
    id: str
    execution_id: str  # FK para Job (execução do crawler)
    url: str
    filename: str

    # File metadata
    file_type: Optional[str] = None  # ex: 'pdf', 'jpg', 'css'
    mime_type: Optional[str] = None  # ex: 'application/pdf'
    size_bytes: int = 0

    # MinIO storage
    minio_path: Optional[str] = None  # ex: 'crawled/{execution_id}/files/document.pdf'
    minio_bucket: str = "ingestify-crawled"
    public_url: Optional[str] = None

    # Status tracking
    status: FileStatus = FileStatus.PENDING
    error_message: Optional[str] = None

    # Timestamps
    downloaded_at: Optional[datetime] = None
    created_at: datetime = None

    def __post_init__(self):
        """Validações pós-inicialização"""
        if self.created_at is None:
            self.created_at = datetime.utcnow()

        # Validar size_bytes
        if self.size_bytes < 0:
            raise ValueError(f"size_bytes cannot be negative: {self.size_bytes}")

        # Validar URL
        if not self.url or not self.url.startswith(('http://', 'https://')):
            raise ValueError(f"Invalid URL: {self.url}")

    def mark_success(self, minio_path: str, public_url: str, size_bytes: int) -> None:
        """
        Marca arquivo como baixado com sucesso

        Args:
            minio_path: Caminho no MinIO
            public_url: URL pública do arquivo
            size_bytes: Tamanho do arquivo em bytes
        """
        if size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")

        self.status = FileStatus.COMPLETED
        self.minio_path = minio_path
        self.public_url = public_url
        self.size_bytes = size_bytes
        self.downloaded_at = datetime.utcnow()
        self.error_message = None

    def mark_failed(self, error_message: str) -> None:
        """
        Marca arquivo como falha no download

        Args:
            error_message: Mensagem de erro
        """
        if not error_message:
            raise ValueError("error_message cannot be empty")

        self.status = FileStatus.FAILED
        self.error_message = error_message
        self.downloaded_at = datetime.utcnow()

    def mark_skipped(self, reason: str) -> None:
        """
        Marca arquivo como pulado (ex: já existe, muito grande)

        Args:
            reason: Razão para pular
        """
        self.status = FileStatus.SKIPPED
        self.error_message = f"Skipped: {reason}"

    def start_download(self) -> None:
        """Marca que o download está em andamento"""
        self.status = FileStatus.DOWNLOADING

    @property
    def is_completed(self) -> bool:
        """Verifica se download foi completado"""
        return self.status == FileStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Verifica se download falhou"""
        return self.status == FileStatus.FAILED

    @property
    def is_downloadable(self) -> bool:
        """Verifica se arquivo pode ser baixado"""
        return self.status in [FileStatus.PENDING, FileStatus.FAILED]

    @property
    def size_mb(self) -> float:
        """Retorna tamanho em MB"""
        return self.size_bytes / (1024 * 1024)

    @property
    def size_kb(self) -> float:
        """Retorna tamanho em KB"""
        return self.size_bytes / 1024

    def calculate_download_speed(self, start_time: datetime, end_time: datetime) -> float:
        """
        Calcula velocidade de download em MB/s

        Args:
            start_time: Tempo de início do download
            end_time: Tempo de fim do download

        Returns:
            Velocidade em MB/s
        """
        if start_time >= end_time:
            return 0.0

        duration_seconds = (end_time - start_time).total_seconds()
        if duration_seconds == 0:
            return 0.0

        size_mb = self.size_mb
        return size_mb / duration_seconds

    def to_dict(self) -> dict:
        """Converte para dicionário"""
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "url": self.url,
            "filename": self.filename,
            "file_type": self.file_type,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "minio_path": self.minio_path,
            "minio_bucket": self.minio_bucket,
            "public_url": self.public_url,
            "status": self.status.value,
            "error_message": self.error_message,
            "downloaded_at": self.downloaded_at.isoformat() if self.downloaded_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @staticmethod
    def from_dict(data: dict) -> "CrawledFile":
        """Cria CrawledFile a partir de dicionário"""
        return CrawledFile(
            id=data["id"],
            execution_id=data["execution_id"],
            url=data["url"],
            filename=data["filename"],
            file_type=data.get("file_type"),
            mime_type=data.get("mime_type"),
            size_bytes=data.get("size_bytes", 0),
            minio_path=data.get("minio_path"),
            minio_bucket=data.get("minio_bucket", "ingestify-crawled"),
            public_url=data.get("public_url"),
            status=FileStatus(data.get("status", "pending")),
            error_message=data.get("error_message"),
            downloaded_at=datetime.fromisoformat(data["downloaded_at"]) if data.get("downloaded_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
        )
