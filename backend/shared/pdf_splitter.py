import os
from pathlib import Path
from typing import List, Tuple
import logging
from PyPDF2 import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


class PDFSplitter:
    """Divide PDFs em páginas individuais para processamento paralelo"""

    def __init__(self, temp_dir: Path):
        """
        Args:
            temp_dir: Diretório temporário para salvar páginas
        """
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def is_pdf(self, file_path: Path) -> bool:
        """Verifica se arquivo é PDF"""
        return file_path.suffix.lower() == '.pdf'

    def get_page_count(self, pdf_path: Path) -> int:
        """Retorna número de páginas do PDF"""
        try:
            reader = PdfReader(str(pdf_path))
            return len(reader.pages)
        except Exception as e:
            logger.error(f"Erro ao contar páginas: {e}")
            raise

    def split_pdf(self, pdf_path: Path) -> List[Tuple[int, Path]]:
        """
        Divide PDF em páginas individuais

        Args:
            pdf_path: Caminho do PDF original

        Returns:
            Lista de tuplas (page_number, page_file_path)
        """
        if not self.is_pdf(pdf_path):
            raise ValueError(f"Arquivo não é PDF: {pdf_path}")

        logger.info(f"Dividindo PDF: {pdf_path}")

        try:
            reader = PdfReader(str(pdf_path))
            total_pages = len(reader.pages)

            logger.info(f"PDF tem {total_pages} páginas")

            page_files = []

            for page_num in range(total_pages):
                # Criar writer para página única
                writer = PdfWriter()
                writer.add_page(reader.pages[page_num])

                # Salvar página individual
                page_filename = f"page_{page_num + 1:04d}.pdf"
                page_path = self.temp_dir / page_filename

                with open(page_path, 'wb') as output_file:
                    writer.write(output_file)

                page_files.append((page_num + 1, page_path))
                logger.debug(f"Página {page_num + 1}/{total_pages} salva: {page_path}")

            logger.info(f"PDF dividido em {len(page_files)} páginas")
            return page_files

        except Exception as e:
            logger.error(f"Erro ao dividir PDF: {e}", exc_info=True)
            raise

    def extract_single_page(self, pdf_path: Path, page_number: int) -> Path:
        """
        Extrai uma página específica do PDF

        Args:
            pdf_path: Caminho do PDF original
            page_number: Número da página (1-indexed)

        Returns:
            Caminho do arquivo da página extraída
        """
        if not self.is_pdf(pdf_path):
            raise ValueError(f"Arquivo não é PDF: {pdf_path}")

        logger.info(f"Extraindo página {page_number} de {pdf_path}")

        try:
            reader = PdfReader(str(pdf_path))
            total_pages = len(reader.pages)

            if page_number < 1 or page_number > total_pages:
                raise ValueError(f"Número de página inválido: {page_number}. PDF tem {total_pages} páginas.")

            # Criar writer para página única (page_number é 1-indexed, mas reader.pages é 0-indexed)
            writer = PdfWriter()
            writer.add_page(reader.pages[page_number - 1])

            # Salvar página individual
            page_filename = f"page_{page_number:04d}.pdf"
            page_path = self.temp_dir / page_filename

            with open(page_path, 'wb') as output_file:
                writer.write(output_file)

            logger.info(f"Página {page_number} extraída: {page_path}")
            return page_path

        except Exception as e:
            logger.error(f"Erro ao extrair página {page_number}: {e}", exc_info=True)
            raise

    def cleanup_pages(self, page_files: List[Tuple[int, Path]]):
        """Remove arquivos de páginas temporárias"""
        for _, page_path in page_files:
            try:
                if page_path.exists():
                    page_path.unlink()
                    logger.debug(f"Página removida: {page_path}")
            except Exception as e:
                logger.warning(f"Erro ao remover página {page_path}: {e}")


def should_split_pdf(file_path: Path, min_pages: int = 2) -> bool:
    """
    Verifica se PDF deve ser dividido

    Args:
        file_path: Caminho do arquivo
        min_pages: Número mínimo de páginas para dividir (default: 2)

    Returns:
        True se deve dividir, False caso contrário
    """
    if not file_path.suffix.lower() == '.pdf':
        return False

    try:
        reader = PdfReader(str(file_path))
        page_count = len(reader.pages)
        return page_count >= min_pages
    except Exception as e:
        logger.warning(f"Erro ao verificar PDF: {e}")
        return False
