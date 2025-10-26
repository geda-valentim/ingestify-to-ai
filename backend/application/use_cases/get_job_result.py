"""
Get Job Result Use Case - Retrieves converted markdown result

Retorna resultado final de conversão
"""
import logging
from typing import Optional

from domain.entities.job import Job, JobStatus, JobType
from domain.repositories.job_repository import JobRepository
from application.ports.storage_port import StoragePort
from application.dto.job_response_dto import JobResultResponseDTO

logger = logging.getLogger(__name__)


class GetJobResultUseCase:
    """
    Use Case: Obter Resultado de Job

    Responsabilidades:
    - Verificar que job está completo
    - Buscar resultado do storage
    - Retornar markdown e metadata
    """

    def __init__(
        self,
        job_repository: JobRepository,
        storage: StoragePort
    ):
        """
        Inicializa use case

        Args:
            job_repository: Repositório de jobs
            storage: Storage de resultados
        """
        self.job_repository = job_repository
        self.storage = storage

    async def execute(self, job_id: str, user_id: str) -> JobResultResponseDTO:
        """
        Executa busca de resultado

        Args:
            job_id: Job ID
            user_id: User ID (para ownership)

        Returns:
            JobResultResponseDTO

        Raises:
            JobNotFoundError: Se job não existe
            UnauthorizedError: Se user não é dono
            JobNotCompletedError: Se job não está completo
            ResultNotFoundError: Se resultado não encontrado
        """
        logger.info(f"Getting result for job {job_id}, user={user_id}")

        # 1. Buscar job
        job = await self.job_repository.find_by_id(job_id)

        if not job:
            raise JobNotFoundError(f"Job {job_id} not found")

        # 2. Verificar ownership
        if job.user_id != user_id:
            raise UnauthorizedError(f"User {user_id} does not own job {job_id}")

        # 3. Verificar se está completo
        if job.status != JobStatus.COMPLETED:
            raise JobNotCompletedError(
                f"Job {job_id} is not completed yet (status: {job.status.value})"
            )

        # 4. Buscar resultado do storage
        result_data = await self.storage.get_job_result(job_id)

        if not result_data:
            raise ResultNotFoundError(f"Result for job {job_id} not found or expired")

        # 5. Montar resposta
        response = JobResultResponseDTO(
            job_id=job.id,
            type=job.job_type.value,
            status="completed",
            result=result_data,
            completed_at=job.completed_at,
            page_number=job.page_number if job.job_type == JobType.PAGE else None,
            parent_job_id=job.parent_job_id if job.job_type == JobType.PAGE else None
        )

        logger.info(
            f"Result retrieved for job {job_id}: "
            f"{len(result_data.get('markdown', ''))} characters"
        )

        return response


class JobNotFoundError(Exception):
    """Job não encontrado"""
    pass


class UnauthorizedError(Exception):
    """Usuário não autorizado"""
    pass


class JobNotCompletedError(Exception):
    """Job ainda não completou"""
    pass


class ResultNotFoundError(Exception):
    """Resultado não encontrado"""
    pass
