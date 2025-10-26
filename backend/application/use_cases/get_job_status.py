"""
Get Job Status Use Case - Retrieves job status with progress

Retorna status detalhado de um job, incluindo páginas para PDFs
"""
import logging
from datetime import datetime
from typing import Optional

from domain.entities.job import Job, JobType
from domain.repositories.job_repository import JobRepository
from domain.repositories.page_repository import PageRepository
from domain.services.progress_calculator_service import ProgressCalculatorService
from application.dto.job_response_dto import JobStatusResponseDTO, PageInfoDTO

logger = logging.getLogger(__name__)


class GetJobStatusUseCase:
    """
    Use Case: Obter Status de Job

    Responsabilidades:
    - Buscar job no repositório
    - Buscar páginas (se PDF multi-página)
    - Calcular progresso dinâmico
    - Montar resposta com informações completas
    """

    def __init__(
        self,
        job_repository: JobRepository,
        page_repository: PageRepository,
        progress_calculator: ProgressCalculatorService
    ):
        """
        Inicializa use case

        Args:
            job_repository: Repositório de jobs
            page_repository: Repositório de páginas
            progress_calculator: Serviço de cálculo de progresso
        """
        self.job_repository = job_repository
        self.page_repository = page_repository
        self.progress_calculator = progress_calculator

    async def execute(self, job_id: str, user_id: str) -> JobStatusResponseDTO:
        """
        Executa busca de status

        Args:
            job_id: Job ID
            user_id: User ID (para verificação de ownership)

        Returns:
            JobStatusResponseDTO

        Raises:
            JobNotFoundError: Se job não existe
            UnauthorizedError: Se user não é dono do job
        """
        logger.info(f"Getting status for job {job_id}, user={user_id}")

        # 1. Buscar job
        job = await self.job_repository.find_by_id(job_id)

        if not job:
            raise JobNotFoundError(f"Job {job_id} not found")

        # 2. Verificar ownership
        if job.user_id != user_id:
            raise UnauthorizedError(f"User {user_id} does not own job {job_id}")

        # 3. Montar resposta base
        response = JobStatusResponseDTO(
            job_id=job.id,
            type=job.job_type.value,
            status=job.status.value,
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error=job.error_message,
            name=job.name,
            parent_job_id=job.parent_job_id,
            page_number=job.page_number,
        )

        # 4. Se MAIN job com múltiplas páginas, adicionar info de páginas
        if job.job_type == JobType.MAIN and job.is_multi_page_pdf():
            pages = await self.page_repository.find_by_job_id(job_id)

            response.total_pages = job.total_pages
            response.pages_completed = job.pages_completed
            response.pages_failed = job.pages_failed

            # Adicionar lista detalhada de páginas
            response.pages = [
                PageInfoDTO(
                    page_number=page.page_number,
                    job_id=page.page_job_id or f"page-{page.page_number}",
                    status=page.status.value,
                    url=f"/jobs/{page.page_job_id or job_id}/result"
                )
                for page in sorted(pages, key=lambda p: p.page_number)
            ]

            # Recalcular progresso baseado em páginas completadas
            if pages:
                calculated_progress = self.progress_calculator.calculate_multi_page_pdf_progress(
                    job=job,
                    pages=pages,
                    split_completed=True,
                    merge_completed=job.status.value == "completed"
                )
                response.progress = int(calculated_progress)

        # 5. Adicionar child jobs info (se houver)
        if job.child_job_ids:
            response.child_jobs = {
                "split_job_id": None,
                "page_job_ids": job.child_job_ids,
                "merge_job_id": None
            }

        logger.info(f"Job {job_id} status: {job.status.value}, progress: {response.progress}%")

        return response


class JobNotFoundError(Exception):
    """Job não encontrado"""
    pass


class UnauthorizedError(Exception):
    """Usuário não autorizado"""
    pass
