"""
Progress Calculator Service - Domain logic for calculating job progress

Calcula progresso de jobs baseado em diferentes critérios
"""
from typing import List
from domain.entities.job import Job, JobStatus
from domain.entities.page import Page, PageStatus
from domain.value_objects.progress import Progress


class ProgressCalculatorService:
    """
    Serviço de domínio para cálculo de progresso

    Encapsula regras de negócio sobre como calcular progresso
    """

    # Weights para cada fase do processamento
    DOWNLOAD_WEIGHT = 20  # 20% para download/preparação
    PAGES_WEIGHT = 70     # 70% para processamento de páginas
    MERGE_WEIGHT = 10     # 10% para merge final

    @staticmethod
    def calculate_single_document_progress(job: Job) -> Progress:
        """
        Calcula progresso para documento único (não-PDF ou PDF single-page)

        Fases:
        - 0%: queued
        - 20%: download/preparação
        - 50%: conversão iniciada
        - 80%: conversão completa
        - 90%: armazenamento
        - 100%: concluído

        Args:
            job: Job entity

        Returns:
            Progress value object
        """
        if job.status == JobStatus.QUEUED:
            return Progress.zero()
        elif job.status == JobStatus.PROCESSING:
            # Se não tem progress explícito, assume 50%
            return Progress(value=job.progress if job.progress > 0 else 50)
        elif job.status == JobStatus.COMPLETED:
            return Progress.complete()
        elif job.status == JobStatus.FAILED:
            return Progress(value=0)
        else:
            return Progress.zero()

    @staticmethod
    def calculate_multi_page_pdf_progress(
        job: Job,
        pages: List[Page],
        split_completed: bool = True,
        merge_completed: bool = False
    ) -> Progress:
        """
        Calcula progresso para PDF multi-página

        Distribuição:
        - 20%: Download + Split
        - 70%: Processamento de páginas
        - 10%: Merge final

        Args:
            job: Main job entity
            pages: Lista de páginas
            split_completed: Se split job foi completado
            merge_completed: Se merge job foi completado

        Returns:
            Progress value object
        """
        if not pages:
            return Progress.zero()

        # Base: download + split (20%)
        base_progress = ProgressCalculatorService.DOWNLOAD_WEIGHT if split_completed else 10

        # Páginas completadas
        completed_count = sum(1 for p in pages if p.status == PageStatus.COMPLETED)
        total_pages = len(pages)

        # Progresso das páginas (70%)
        if total_pages > 0:
            pages_progress = int((completed_count / total_pages) * ProgressCalculatorService.PAGES_WEIGHT)
        else:
            pages_progress = 0

        # Merge (10%)
        merge_progress = ProgressCalculatorService.MERGE_WEIGHT if merge_completed else 0

        total_progress = base_progress + pages_progress + merge_progress

        return Progress(value=min(total_progress, 100))

    @staticmethod
    def is_all_pages_completed(pages: List[Page]) -> bool:
        """
        Verifica se todas as páginas foram completadas

        Args:
            pages: Lista de páginas

        Returns:
            True se todas completadas
        """
        if not pages:
            return False

        return all(p.status == PageStatus.COMPLETED for p in pages)

    @staticmethod
    def has_any_page_failed(pages: List[Page]) -> bool:
        """
        Verifica se alguma página falhou

        Args:
            pages: Lista de páginas

        Returns:
            True se alguma falhou
        """
        return any(p.status == PageStatus.FAILED for p in pages)

    @staticmethod
    def calculate_success_rate(pages: List[Page]) -> float:
        """
        Calcula taxa de sucesso de páginas

        Args:
            pages: Lista de páginas

        Returns:
            Taxa de sucesso (0.0 a 1.0)
        """
        if not pages:
            return 0.0

        completed = sum(1 for p in pages if p.status == PageStatus.COMPLETED)
        return completed / len(pages)
