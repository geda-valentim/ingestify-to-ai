"""
Get Crawler Job Use Case - Retrieves crawler job details

Use case para buscar detalhes de um crawler job.
"""
import logging
from typing import Optional

from domain.entities.crawler_job import CrawlerJob
from domain.repositories.crawler_job_repository import CrawlerJobRepository
from application.dto.crawler_job_dto import CrawlerJobDTO, CrawlerConfigDTO, CrawlerScheduleDTO

logger = logging.getLogger(__name__)


class GetCrawlerJobUseCase:
    """
    Use Case: Obter Crawler Job

    Responsabilidades:
    - Buscar job no repositório
    - Verificar ownership
    - Converter entidade para DTO
    - Retornar detalhes completos
    """

    def __init__(self, job_repository: CrawlerJobRepository):
        """
        Args:
            job_repository: Repositório de CrawlerJob
        """
        self.job_repository = job_repository

    async def execute(self, job_id: str, user_id: str) -> CrawlerJobDTO:
        """
        Busca crawler job por ID.

        Args:
            job_id: ID do job
            user_id: ID do usuário (para verificação de ownership)

        Returns:
            CrawlerJobDTO com detalhes completos

        Raises:
            JobNotFoundError: Se job não existe
            UnauthorizedError: Se usuário não é dono do job
        """
        logger.info(f"Getting crawler job {job_id} for user {user_id}")

        # 1. Buscar job
        crawler_job = await self.job_repository.find_by_id(job_id)

        if not crawler_job:
            raise JobNotFoundError(f"Crawler job {job_id} not found")

        # 2. Buscar user_id associado ao job (do MySQL Job table)
        job_user_id = await self.job_repository.get_user_id(job_id)

        # 3. Verificar ownership
        if job_user_id != user_id:
            raise UnauthorizedError(f"User {user_id} does not own crawler job {job_id}")

        # 4. Converter para DTO
        dto = self._entity_to_dto(crawler_job, job_user_id)

        logger.info(f"Retrieved crawler job {job_id}")
        return dto

    def _entity_to_dto(self, entity: CrawlerJob, user_id: str) -> CrawlerJobDTO:
        """Converte CrawlerJob entity para DTO"""
        # Config DTO
        config_dto = CrawlerConfigDTO(
            mode=entity.config.mode.value,
            engine=entity.config.engine.value,
            max_depth=entity.config.max_depth,
            max_pages=entity.config.max_pages,
            respect_robots_txt=entity.config.respect_robots_txt,
            follow_external_links=entity.config.follow_external_links,
            max_retries=entity.config.retry_config.max_retries,
            retry_delay_seconds=entity.config.retry_config.retry_delay_seconds,
            download_images=entity.config.asset_config.download_images,
            download_css=entity.config.asset_config.download_css,
            download_js=entity.config.asset_config.download_js,
            use_proxy=entity.config.proxy_config is not None,
            proxy_host=entity.config.proxy_config.host if entity.config.proxy_config else None,
            proxy_port=entity.config.proxy_config.port if entity.config.proxy_config else None,
            proxy_username=entity.config.proxy_config.username if entity.config.proxy_config else None,
            proxy_password=None  # Não retornar senha
        )

        # Schedule DTO (opcional)
        schedule_dto = None
        if entity.schedule:
            schedule_dto = CrawlerScheduleDTO(
                schedule_type=entity.schedule.schedule_type,
                cron_expression=entity.schedule.cron_expression,
                timezone=entity.schedule.timezone,
                next_runs=entity.schedule.next_runs
            )

        # Next execution (primeira da lista de next_runs)
        next_execution = None
        if entity.schedule and entity.schedule.next_runs:
            next_execution = entity.schedule.next_runs[0]

        return CrawlerJobDTO(
            id=entity.id,
            user_id=user_id,
            name=entity.name,
            source_url=entity.source_url,
            status=entity.status.value,
            config=config_dto,
            schedule=schedule_dto,
            total_executions=entity.total_executions,
            successful_executions=entity.successful_executions,
            failed_executions=entity.failed_executions,
            last_execution=entity.last_execution,
            next_execution=next_execution,
            created_at=entity.created_at,
            updated_at=entity.updated_at
        )


class JobNotFoundError(Exception):
    """Job não encontrado"""
    pass


class UnauthorizedError(Exception):
    """Usuário não autorizado"""
    pass
