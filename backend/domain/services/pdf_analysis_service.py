"""
PDF Analysis Service - Domain logic for PDF analysis

Determina se um PDF deve ser dividido em páginas para processamento paralelo
"""
import subprocess
from pathlib import Path
from typing import Optional


class PDFAnalysisService:
    """
    Serviço de domínio para análise de PDFs

    Encapsula regras de negócio sobre quando dividir PDFs
    """

    @staticmethod
    def should_split_pdf(
        file_path: Path,
        min_pages: int = 2,
        max_file_size_mb: Optional[float] = None
    ) -> bool:
        """
        Determina se PDF deve ser dividido em páginas

        Regras de negócio:
        - PDFs com >= min_pages devem ser divididos
        - PDFs muito grandes devem ser divididos mesmo com poucas páginas
        - Apenas arquivos PDF são elegíveis

        Args:
            file_path: Caminho do arquivo
            min_pages: Mínimo de páginas para split (padrão: 2)
            max_file_size_mb: Tamanho máximo antes de forçar split (opcional)

        Returns:
            True se deve dividir, False caso contrário
        """
        # Apenas PDFs podem ser divididos
        if not PDFAnalysisService.is_pdf(file_path):
            return False

        # Contar páginas do PDF
        page_count = PDFAnalysisService.count_pdf_pages(file_path)

        if page_count is None:
            return False  # Não conseguiu contar, não divide

        # Regra principal: >= min_pages
        if page_count >= min_pages:
            return True

        # Regra secundária: arquivo muito grande
        if max_file_size_mb:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > max_file_size_mb:
                return True

        return False

    @staticmethod
    def is_pdf(file_path: Path) -> bool:
        """
        Verifica se arquivo é PDF

        Args:
            file_path: Caminho do arquivo

        Returns:
            True se é PDF
        """
        if not file_path.exists():
            return False

        # Check extension
        if file_path.suffix.lower() != '.pdf':
            return False

        # Check file signature (magic bytes)
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
                return header == b'%PDF'
        except Exception:
            return False

    @staticmethod
    def count_pdf_pages(file_path: Path) -> Optional[int]:
        """
        Conta número de páginas de um PDF usando qpdf

        Args:
            file_path: Caminho do arquivo PDF

        Returns:
            Número de páginas ou None se falhar
        """
        try:
            result = subprocess.run(
                ['qpdf', '--show-npages', str(file_path)],
                capture_output=True,
                text=True,
                check=True
            )
            return int(result.stdout.strip())
        except Exception:
            # Fallback: try with pdfplumber if available
            try:
                import pdfplumber
                with pdfplumber.open(str(file_path)) as pdf:
                    return len(pdf.pages)
            except Exception:
                return None

    @staticmethod
    def estimate_processing_time(page_count: int, seconds_per_page: float = 5.0) -> float:
        """
        Estima tempo de processamento baseado em páginas

        Args:
            page_count: Número de páginas
            seconds_per_page: Tempo médio por página

        Returns:
            Tempo estimado em segundos
        """
        return page_count * seconds_per_page
