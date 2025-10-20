"""
DocumentInfo Value Object - Contains document metadata
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DocumentInfo:
    """
    Value Object para informações do documento

    Metadata imutável sobre o documento convertido
    """
    filename: str
    mime_type: str
    file_size_bytes: int
    source_type: str  # file, url, gdrive, dropbox

    # PDF-specific
    total_pages: Optional[int] = None

    # Derived metadata
    source_url: Optional[str] = None

    def __post_init__(self):
        """Validações"""
        self._validate_file_size()
        self._validate_source_type()

    def _validate_file_size(self):
        """Valida tamanho do arquivo"""
        if self.file_size_bytes < 0:
            raise ValueError(f"File size must be >= 0, got {self.file_size_bytes}")

    def _validate_source_type(self):
        """Valida tipo de fonte"""
        valid_sources = ["file", "url", "gdrive", "dropbox"]
        if self.source_type not in valid_sources:
            raise ValueError(f"Invalid source_type: {self.source_type}. Must be one of {valid_sources}")

    def is_pdf(self) -> bool:
        """Verifica se é PDF"""
        return self.mime_type == "application/pdf" or self.filename.lower().endswith(".pdf")

    def is_multi_page_pdf(self) -> bool:
        """Verifica se é PDF multi-página"""
        return self.is_pdf() and self.total_pages is not None and self.total_pages > 1

    def file_size_mb(self) -> float:
        """Retorna tamanho em MB"""
        return self.file_size_bytes / (1024 * 1024)

    def __str__(self) -> str:
        return f"{self.filename} ({self.file_size_mb():.2f} MB)"
