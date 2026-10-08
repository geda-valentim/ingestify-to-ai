import os
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
import logging
from shared.minio_client import get_minio_client

logger = logging.getLogger(__name__)



# qpdf exits 3 when it finished the job but warned about the input (e.g. a damaged
# cross-reference table it rebuilt): that is a success, not a failure. Treating it as
# one failed real course PDFs on 2026-10-08. `--warning-exit-0` maps it to 0; the
# warnings are still logged.
QPDF = ["qpdf", "--warning-exit-0"]


def _qpdf(args: List[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(QPDF + args, capture_output=True, text=True, check=True)
    warnings = (getattr(result, "stderr", "") or "").strip()
    if warnings:
        logger.warning("qpdf warnings for %s: %s", args[0] if args else "?", warnings[:500])
    return result


def _pypdf_page_count(pdf_path: Path) -> int:
    from PyPDF2 import PdfReader

    return len(PdfReader(str(pdf_path), strict=False).pages)


def count_pages(pdf_path: Path) -> int:
    """Page count via qpdf, falling back to PyPDF2 when qpdf refuses the file."""
    try:
        return int(_qpdf(["--show-npages", str(pdf_path)]).stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        stderr = getattr(e, "stderr", "") or str(e)
        logger.warning("qpdf could not count pages of %s (%s); trying PyPDF2", pdf_path, stderr.strip()[:300])
        try:
            return _pypdf_page_count(pdf_path)
        except Exception:
            raise e  # neither could read it: report qpdf's error, the primary tool


def extract_page(pdf_path: Path, page_number: int, page_path: Path) -> None:
    """
    Write page `page_number` (1-based) of `pdf_path` to `page_path`.

    qpdf first (it drops unused objects, so pages stay small); PyPDF2 when qpdf
    fails outright. Either way the output must open and hold exactly one page.
    """
    try:
        _qpdf([str(pdf_path), "--pages", ".", f"{page_number}-{page_number}", "--", str(page_path)])
    except subprocess.CalledProcessError as e:
        logger.warning("qpdf could not extract page %s of %s (%s); trying PyPDF2",
                       page_number, pdf_path, (e.stderr or "").strip()[:300])
        from PyPDF2 import PdfReader, PdfWriter

        writer = PdfWriter()
        writer.add_page(PdfReader(str(pdf_path), strict=False).pages[page_number - 1])
        with open(page_path, "wb") as out:
            writer.write(out)
    if not page_path.exists() or page_path.stat().st_size == 0 or _pypdf_page_count(page_path) != 1:
        raise ValueError(f"PAGE_EXTRACTION_INVALID: página {page_number} não pôde ser extraída de {pdf_path.name}")


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
            return count_pages(pdf_path)
        except Exception as e:
            logger.error(f"Erro ao contar páginas: {e}")
            raise

    def split_pdf(self, pdf_path: Path, job_id: Optional[str] = None, upload_to_minio: bool = True) -> List[Tuple[int, Path, Optional[str]]]:
        """
        Divide PDF em páginas individuais e opcionalmente faz upload para MinIO
        Usa qpdf para evitar explosão de tamanho dos arquivos.

        Args:
            pdf_path: Caminho do PDF original
            job_id: ID do job (usado para organizar no MinIO)
            upload_to_minio: Se True, faz upload das páginas para MinIO

        Returns:
            Lista de tuplas (page_number, local_page_path, minio_path)
        """
        if not self.is_pdf(pdf_path):
            raise ValueError(f"Arquivo não é PDF: {pdf_path}")

        logger.info(f"Dividindo PDF com qpdf: {pdf_path}")

        try:
            total_pages = self.get_page_count(pdf_path)
            logger.info(f"PDF tem {total_pages} páginas")

            page_files = []
            minio_client = get_minio_client() if upload_to_minio else None

            for page_num in range(1, total_pages + 1):
                # Salvar página individual usando qpdf
                page_filename = f"page_{page_num:04d}.pdf"
                page_path = self.temp_dir / page_filename

                # Usar qpdf para extrair página (remove objetos não utilizados)
                extract_page(pdf_path, page_num, page_path)

                # Upload para MinIO se habilitado
                minio_path = None
                if minio_client and job_id:
                    minio_object_name = f"pages/{job_id}/{page_filename}"
                    try:
                        minio_client.upload_file(
                            bucket_name=minio_client.bucket_pages,
                            object_name=minio_object_name,
                            file_path=str(page_path),
                            content_type="application/pdf",
                        )
                        minio_path = minio_object_name
                        logger.debug(f"Página {page_num} enviada para MinIO: {minio_path}")
                    except Exception as e:
                        logger.error(f"Erro ao enviar página {page_num} para MinIO: {e}")
                        # Continua mesmo com erro no MinIO

                page_files.append((page_num, page_path, minio_path))
                logger.debug(f"Página {page_num}/{total_pages} salva: {page_path}")

            logger.info(f"PDF dividido em {len(page_files)} páginas com qpdf")
            return page_files

        except Exception as e:
            logger.error(f"Erro ao dividir PDF: {e}", exc_info=True)
            raise

    def extract_single_page(self, pdf_path: Path, page_number: int, job_id: Optional[str] = None, upload_to_minio: bool = True) -> Tuple[Path, Optional[str]]:
        """
        Extrai uma página específica do PDF e opcionalmente faz upload para MinIO
        Usa qpdf para evitar explosão de tamanho dos arquivos.

        Args:
            pdf_path: Caminho do PDF original
            page_number: Número da página (1-indexed)
            job_id: ID do job (usado para organizar no MinIO)
            upload_to_minio: Se True, faz upload da página para MinIO

        Returns:
            Tupla (local_page_path, minio_path)
        """
        if not self.is_pdf(pdf_path):
            raise ValueError(f"Arquivo não é PDF: {pdf_path}")

        logger.info(f"Extraindo página {page_number} de {pdf_path} com qpdf")

        try:
            total_pages = self.get_page_count(pdf_path)

            if page_number < 1 or page_number > total_pages:
                raise ValueError(f"Número de página inválido: {page_number}. PDF tem {total_pages} páginas.")

            # Salvar página individual usando qpdf
            page_filename = f"page_{page_number:04d}.pdf"
            page_path = self.temp_dir / page_filename

            # Usar qpdf para extrair página (remove objetos não utilizados)
            extract_page(pdf_path, page_number, page_path)

            # Upload para MinIO se habilitado
            minio_path = None
            if upload_to_minio and job_id:
                minio_client = get_minio_client()
                minio_object_name = f"pages/{job_id}/{page_filename}"
                try:
                    minio_client.upload_file(
                        bucket_name=minio_client.bucket_pages,
                        object_name=minio_object_name,
                        file_path=str(page_path),
                        content_type="application/pdf",
                    )
                    minio_path = minio_object_name
                    logger.debug(f"Página {page_number} enviada para MinIO: {minio_path}")
                except Exception as e:
                    logger.error(f"Erro ao enviar página {page_number} para MinIO: {e}")

            logger.info(f"Página {page_number} extraída com qpdf: {page_path}")
            return page_path, minio_path

        except Exception as e:
            logger.error(f"Erro ao extrair página {page_number}: {e}", exc_info=True)
            raise

    def cleanup_pages(self, page_files: List[Tuple[int, Path, Optional[str]]], cleanup_minio: bool = True):
        """
        Remove arquivos de páginas temporárias do filesystem e opcionalmente do MinIO

        Args:
            page_files: Lista de tuplas (page_number, local_path, minio_path)
            cleanup_minio: Se True, remove também do MinIO
        """
        minio_client = get_minio_client() if cleanup_minio else None

        for page_data in page_files:
            # Handle both old format (page_num, path) and new format (page_num, path, minio_path)
            if len(page_data) == 2:
                page_num, page_path = page_data
                minio_path = None
            else:
                page_num, page_path, minio_path = page_data

            # Cleanup local file
            try:
                if page_path.exists():
                    page_path.unlink()
                    logger.debug(f"Página local removida: {page_path}")
            except Exception as e:
                logger.warning(f"Erro ao remover página local {page_path}: {e}")

            # Cleanup MinIO file
            if minio_client and minio_path:
                try:
                    minio_client.delete_file(
                        bucket_name=minio_client.bucket_pages,
                        object_name=minio_path
                    )
                    logger.debug(f"Página removida do MinIO: {minio_path}")
                except Exception as e:
                    logger.warning(f"Erro ao remover página do MinIO {minio_path}: {e}")


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
        return count_pages(file_path) >= min_pages
    except Exception as e:
        logger.warning(f"Erro ao verificar PDF com qpdf: {e}")
        return False
