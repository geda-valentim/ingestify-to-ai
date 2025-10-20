"""
Converter Port - Interface for document conversion

Abstração para motor de conversão (Docling, etc.)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ConversionResult:
    """Resultado de uma conversão"""
    markdown: str
    metadata: Dict[str, Any]

    @property
    def char_count(self) -> int:
        """Retorna contagem de caracteres"""
        return len(self.markdown)

    @property
    def word_count(self) -> int:
        """Retorna contagem de palavras"""
        return len(self.markdown.split())


class ConverterPort(ABC):
    """
    Interface para conversor de documentos

    Implementações podem usar Docling, Pandoc, etc.
    """

    @abstractmethod
    async def convert_to_markdown(
        self,
        file_path: Path,
        options: Dict[str, Any] = None
    ) -> ConversionResult:
        """
        Converte documento para Markdown

        Args:
            file_path: Caminho do arquivo
            options: Opções de conversão (ex: enable_ocr, enable_tables)

        Returns:
            ConversionResult with markdown and metadata

        Raises:
            ConversionError: Se conversão falhar
        """
        pass

    @abstractmethod
    async def detect_format(self, file_path: Path) -> str:
        """
        Detecta formato do documento

        Args:
            file_path: Caminho do arquivo

        Returns:
            Format string (pdf, docx, html, etc.)
        """
        pass

    @abstractmethod
    async def is_supported(self, file_path: Path) -> bool:
        """
        Verifica se formato é suportado

        Args:
            file_path: Caminho do arquivo

        Returns:
            True se suportado
        """
        pass


class ConversionError(Exception):
    """Erro durante conversão"""
    pass
