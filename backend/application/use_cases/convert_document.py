"""
Convert Document Use Case - Orchestrates document conversion

Esta é a lógica principal de conversão de documentos.
Segue Clean Architecture: depende apenas de abstrações (ports/repositories).
"""
import logging
from pathlib import Path
from datetime import datetime

from domain.entities.job import Job, JobStatus, JobType
from domain.value_objects.job_id import JobId
from domain.repositories.job_repository import JobRepository
from application.ports.queue_port import QueuePort
from application.dto.convert_request_dto import ConvertRequestDTO
from application.dto.job_response_dto import JobResponseDTO

logger = logging.getLogger(__name__)


class ConvertDocumentUseCase:
    """
    Use Case: Converter Documento

    Responsabilidades:
    - Criar job principal (MAIN)
    - Enfileirar para processamento
    - Retornar resposta com job_id

    Não contém lógica de infraestrutura (Redis, MySQL, Celery)
    """

    def __init__(
        self,
        job_repository: JobRepository,
        queue: QueuePort
    ):
        """
        Inicializa use case com dependências injetadas

        Args:
            job_repository: Repositório de jobs
            queue: Sistema de filas
        """
        self.job_repository = job_repository
        self.queue = queue

    async def execute(self, request: ConvertRequestDTO) -> JobResponseDTO:
        """
        Executa conversão de documento

        Args:
            request: ConvertRequestDTO

        Returns:
            JobResponseDTO com job_id

        Raises:
            ValueError: Se parâmetros inválidos
            Exception: Se erro ao criar job
        """
        logger.info(
            f"Converting document: user={request.user_id}, "
            f"source_type={request.source_type}, source={request.source[:50]}"
        )

        # 1. Gerar Job ID
        job_id = JobId.generate()

        # 2. Criar entidade Job (MAIN)
        job = Job(
            id=str(job_id),
            user_id=request.user_id,
            job_type=JobType.MAIN,
            status=JobStatus.QUEUED,
            filename=request.filename,
            source_type=request.source_type,
            source_url=request.source if request.source_type != "file" else None,
            file_size_bytes=request.file_size_bytes,
            mime_type=request.mime_type,
            name=request.display_name,
            progress=0,
            created_at=datetime.utcnow(),
        )

        # 3. Persistir job
        try:
            await self.job_repository.save(job)
            logger.info(f"Job {job.id} saved to repository")
        except Exception as e:
            logger.error(f"Failed to save job {job.id}: {e}", exc_info=True)
            raise

        # 4. Enfileirar para processamento
        try:
            task_id = await self.queue.enqueue_conversion(
                job_id=str(job_id),
                source_type=request.source_type,
                source=request.source,
                options=request.options,
                auth_token=request.auth_token
            )
            logger.info(f"Job {job.id} enqueued with task_id={task_id}")
        except Exception as e:
            logger.error(f"Failed to enqueue job {job.id}: {e}", exc_info=True)

            # Marcar job como failed
            job.mark_as_failed(f"Failed to enqueue: {str(e)}")
            await self.job_repository.save(job)
            raise

        # 5. Retornar resposta
        return JobResponseDTO(
            job_id=str(job_id),
            status="queued",
            created_at=job.created_at,
            message="Job enfileirado para processamento"
        )


class ConvertDocumentError(Exception):
    """Erro durante conversão de documento"""
    pass
