"""
PDF Merger Port - Interface for PDF merging operations

Abstração para merge de PDFs (PyPDF2, etc.)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class PDFBookmark:
    """Bookmark/TOC entry for PDF"""
    title: str
    page_number: int
    level: int = 0  # Nesting level (0 = top level, 1 = sub-bookmark, etc.)


@dataclass
class MergeResult:
    """Resultado de merge de PDFs"""
    output_path: Path
    total_pages: int
    file_size_bytes: int
    source_files_count: int
    success: bool = True
    error: Optional[str] = None

    @property
    def file_size_mb(self) -> float:
        """Retorna tamanho em MB"""
        return self.file_size_bytes / (1024 * 1024)


class PDFMergerPort(ABC):
    """
    Interface para merge de PDFs

    Implementações podem usar PyPDF2, pdftk, etc.
    """

    @abstractmethod
    async def merge_pdfs(
        self,
        pdf_files: List[Path],
        output_path: Path,
        bookmarks: Optional[List[PDFBookmark]] = None
    ) -> MergeResult:
        """
        Merge múltiplos PDFs em um único arquivo

        Args:
            pdf_files: Lista de caminhos dos PDFs para merge
            output_path: Caminho do PDF merged
            bookmarks: Lista opcional de bookmarks para adicionar

        Returns:
            MergeResult com informações do merge

        Raises:
            PDFMergerError: Se merge falhar
        """
        pass

    @abstractmethod
    async def validate_pdf(self, file_path: Path) -> bool:
        """
        Valida se PDF é válido e não está corrompido

        Args:
            file_path: Caminho do PDF

        Returns:
            True se PDF é válido

        Raises:
            PDFMergerError: Se validação falhar
        """
        pass

    @abstractmethod
    async def get_pdf_info(self, file_path: Path) -> Dict[str, any]:
        """
        Extrai informações de um PDF

        Args:
            file_path: Caminho do PDF

        Returns:
            Dict com informações: {
                "page_count": int,
                "file_size_bytes": int,
                "title": str,
                "author": str,
                "created": datetime,
                "modified": datetime,
            }

        Raises:
            PDFMergerError: Se leitura falhar
        """
        pass

    @abstractmethod
    async def add_bookmarks(
        self,
        pdf_file: Path,
        bookmarks: List[PDFBookmark],
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Adiciona bookmarks/TOC a um PDF

        Args:
            pdf_file: PDF de entrada
            bookmarks: Lista de bookmarks
            output_path: PDF de saída (se None, sobrescreve entrada)

        Returns:
            Path do PDF com bookmarks

        Raises:
            PDFMergerError: Se operação falhar
        """
        pass

    @abstractmethod
    async def compress_pdf(
        self,
        pdf_file: Path,
        output_path: Optional[Path] = None,
        compression_level: str = "medium"
    ) -> Path:
        """
        Comprime PDF removendo metadados e otimizando

        Args:
            pdf_file: PDF de entrada
            output_path: PDF de saída (se None, sobrescreve entrada)
            compression_level: Nível de compressão (low, medium, high)

        Returns:
            Path do PDF comprimido

        Raises:
            PDFMergerError: Se compressão falhar
        """
        pass


class PDFMergerError(Exception):
    """Erro durante merge de PDF"""
    pass


class PDFValidationError(PDFMergerError):
    """Erro de validação de PDF"""
    pass


class PDFCorruptedError(PDFMergerError):
    """PDF corrompido"""
    pass
