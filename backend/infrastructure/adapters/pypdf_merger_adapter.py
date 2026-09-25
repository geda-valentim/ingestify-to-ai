"""
PyPDF Merger Adapter

Implementação de PDFMergerPort usando PyPDF2
"""
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import asyncio

from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from PyPDF2.errors import PdfReadError

from application.ports.pdf_merger_port import (
    PDFMergerPort,
    PDFBookmark,
    MergeResult,
    PDFMergerError,
    PDFValidationError,
    PDFCorruptedError,
)

logger = logging.getLogger(__name__)


class PyPDFMergerAdapter(PDFMergerPort):
    """
    Adapter para merge de PDFs usando PyPDF2

    Características:
    - Merge de múltiplos PDFs
    - Validação de integridade
    - Extração de metadados
    - Adição de bookmarks/TOC
    - Compressão básica (remoção de metadados)
    """

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
        """
        try:
            # Validar inputs
            if not pdf_files:
                raise PDFMergerError("No PDF files provided for merging")

            for pdf_file in pdf_files:
                if not pdf_file.exists():
                    raise PDFMergerError(f"PDF file not found: {pdf_file}")

                # Validar cada PDF
                is_valid = await self.validate_pdf(pdf_file)
                if not is_valid:
                    raise PDFValidationError(f"Invalid or corrupted PDF: {pdf_file}")

            # Criar diretório de saída se não existir
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Executar merge em thread separada (PyPDF2 é síncrono)
            merger = PdfMerger()

            for pdf_file in pdf_files:
                merger.append(str(pdf_file))

            # Adicionar bookmarks se fornecidos
            if bookmarks:
                for bookmark in bookmarks:
                    merger.add_outline_item(
                        title=bookmark.title,
                        page_number=bookmark.page_number,
                        parent=None  # Top-level bookmark
                    )

            # Salvar PDF merged
            merger.write(str(output_path))
            merger.close()

            # Obter informações do resultado
            output_info = await self.get_pdf_info(output_path)

            return MergeResult(
                output_path=output_path,
                total_pages=output_info["page_count"],
                file_size_bytes=output_path.stat().st_size,
                source_files_count=len(pdf_files),
                success=True,
            )

        except PDFValidationError:
            raise
        except PDFMergerError:
            raise
        except Exception as e:
            logger.error(f"Error merging PDFs: {e}", exc_info=True)
            raise PDFMergerError(f"Failed to merge PDFs: {e}") from e

    async def validate_pdf(self, file_path: Path) -> bool:
        """
        Valida se PDF é válido e não está corrompido

        Args:
            file_path: Caminho do PDF

        Returns:
            True se PDF é válido
        """
        try:
            if not file_path.exists():
                return False

            # Tentar ler o PDF
            reader = PdfReader(str(file_path))

            # Verificar se tem pelo menos uma página
            if len(reader.pages) == 0:
                return False

            # Tentar acessar primeira página (detecção de corrupção)
            _ = reader.pages[0]

            return True

        except PdfReadError as e:
            logger.warning(f"PDF validation failed for {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error validating PDF {file_path}: {e}")
            return False

    async def get_pdf_info(self, file_path: Path) -> Dict[str, any]:
        """
        Extrai informações de um PDF

        Args:
            file_path: Caminho do PDF

        Returns:
            Dict com informações do PDF
        """
        try:
            if not file_path.exists():
                raise PDFMergerError(f"PDF file not found: {file_path}")

            reader = PdfReader(str(file_path))
            metadata = reader.metadata or {}

            # Extrair informações
            info = {
                "page_count": len(reader.pages),
                "file_size_bytes": file_path.stat().st_size,
                "title": metadata.get("/Title", ""),
                "author": metadata.get("/Author", ""),
                "subject": metadata.get("/Subject", ""),
                "creator": metadata.get("/Creator", ""),
                "producer": metadata.get("/Producer", ""),
            }

            # Parse datas se disponíveis
            created_str = metadata.get("/CreationDate")
            if created_str:
                info["created"] = self._parse_pdf_date(created_str)
            else:
                info["created"] = None

            modified_str = metadata.get("/ModDate")
            if modified_str:
                info["modified"] = self._parse_pdf_date(modified_str)
            else:
                info["modified"] = None

            return info

        except PdfReadError as e:
            logger.error(f"Error reading PDF {file_path}: {e}")
            raise PDFCorruptedError(f"Corrupted PDF: {file_path}") from e
        except Exception as e:
            logger.error(f"Error getting PDF info for {file_path}: {e}", exc_info=True)
            raise PDFMergerError(f"Failed to get PDF info: {e}") from e

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
        """
        try:
            if not pdf_file.exists():
                raise PDFMergerError(f"PDF file not found: {pdf_file}")

            # Determinar caminho de saída
            if output_path is None:
                output_path = pdf_file

            # Ler PDF original
            reader = PdfReader(str(pdf_file))
            writer = PdfWriter()

            # Copiar páginas
            for page in reader.pages:
                writer.add_page(page)

            # Adicionar bookmarks
            for bookmark in bookmarks:
                writer.add_outline_item(
                    title=bookmark.title,
                    page_number=bookmark.page_number,
                )

            # Salvar
            with open(output_path, 'wb') as f:
                writer.write(f)

            logger.info(f"Added {len(bookmarks)} bookmarks to {pdf_file}")
            return output_path

        except Exception as e:
            logger.error(f"Error adding bookmarks to {pdf_file}: {e}", exc_info=True)
            raise PDFMergerError(f"Failed to add bookmarks: {e}") from e

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
        """
        try:
            if not pdf_file.exists():
                raise PDFMergerError(f"PDF file not found: {pdf_file}")

            # Determinar caminho de saída
            if output_path is None:
                output_path = pdf_file

            # Ler PDF original
            reader = PdfReader(str(pdf_file))
            writer = PdfWriter()

            # Copiar páginas com compressão
            for page in reader.pages:
                page.compress_content_streams()  # Comprime streams de conteúdo
                writer.add_page(page)

            # Remover metadados duplicados
            writer.add_metadata({
                "/Producer": "Ingestify PDF Processor",
                "/Creator": "Ingestify",
            })

            # Salvar
            with open(output_path, 'wb') as f:
                writer.write(f)

            # Log de estatísticas
            original_size = pdf_file.stat().st_size
            compressed_size = output_path.stat().st_size
            reduction = ((original_size - compressed_size) / original_size) * 100

            logger.info(
                f"Compressed {pdf_file}: {original_size} → {compressed_size} bytes "
                f"({reduction:.1f}% reduction)"
            )

            return output_path

        except Exception as e:
            logger.error(f"Error compressing {pdf_file}: {e}", exc_info=True)
            raise PDFMergerError(f"Failed to compress PDF: {e}") from e

    @staticmethod
    def _parse_pdf_date(date_str: str) -> Optional[datetime]:
        """
        Parse data no formato PDF (D:YYYYMMDDHHmmSS)

        Args:
            date_str: String de data do PDF

        Returns:
            datetime ou None se parse falhar
        """
        try:
            # Formato PDF: D:20240115120000+00'00'
            if date_str.startswith("D:"):
                date_str = date_str[2:16]  # Extrair YYYYMMDDHHmmSS
                return datetime.strptime(date_str, "%Y%m%d%H%M%S")
            return None
        except Exception:
            return None
