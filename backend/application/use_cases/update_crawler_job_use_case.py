"""
Update Crawler Job Use Case - Updates crawler job configuration

Use case para atualizar configurações de um crawler job existente.
"""
import logging
from typing import List, Optional
from datetime import datetime

from domain.entities.crawler_job import CrawlerJob
from domain.value_objects.crawler_config import CrawlerConfig, RetryConfig, AssetConfig
from domain.value_objects.crawler_schedule import CrawlerSchedule
from domain.value_objects.crawler_enums import CrawlerMode, CrawlerEngine
from domain.value_objects.proxy_config import ProxyConfig
from domain.repositories.crawler_job_repository import CrawlerJobRepository
from application.ports.crawler_search_port import CrawlerSearchPort
from application.dto.update_crawler_job_dto import UpdateCrawlerJobDTO, UpdateCrawlerJobResponseDTO

logger = logging.getLogger(__name__)


class UpdateCrawlerJobUseCase:
    """
    Use Case: Atualizar Crawler Job

    Responsabilidades:
    - Buscar job existente
    - Validar que não está em execução
    - Aplicar mudanças (partial update)
    - Persistir alterações
    - Atualizar índice Elasticsearch
    - Retornar lista de campos alterados
    """

    def __init__(
        self,
        job_repository: CrawlerJobRepository,
        search_adapter: CrawlerSearchPort
    ):
        """
        Args:
            job_repository: Repositório de CrawlerJob
            search_adapter: Adapter para busca (Elasticsearch)
        """
        self.job_repository = job_repository
        self.search_adapter = search_adapter

    async def execute(
        self,
        job_id: str,
        user_id: str,
        dto: UpdateCrawlerJobDTO
    ) -> UpdateCrawlerJobResponseDTO:
        """
        Atualiza crawler job.

        Args:
            job_id: ID do job a atualizar
            user_id: ID do usuário (ownership check)
            dto: Dados a atualizar (partial)

        Returns:
            UpdateCrawlerJobResponseDTO com campos alterados

        Raises:
            JobNotFoundError: Se job não existe
            UnauthorizedError: Se usuário não é dono
            JobInExecutionError: Se job está executando
            ValueError: Se dados inválidos
        """
        logger.info(f"Updating crawler job {job_id} for user {user_id}")

        # 1. Buscar job existente
        crawler_job = await self.job_repository.find_by_id(job_id)
        if not crawler_job:
            raise JobNotFoundError(f"Crawler job {job_id} not found")

        # 2. Verificar ownership
        job_user_id = await self.job_repository.get_user_id(job_id)
        if job_user_id != user_id:
            raise UnauthorizedError(f"User {user_id} does not own crawler job {job_id}")

        # 3. Verificar se pode atualizar (não pode estar processando)
        # Nota: status PROCESSING seria para execuções, não para o job em si
        # Jobs podem ser atualizados a qualquer momento, mas não afetam execuções em andamento

        # 4. Aplicar mudanças (partial update)
        updated_fields = []
        warnings = []

        # Atualizar nome
        if dto.name is not None:
            crawler_job.name = dto.name
            updated_fields.append("name")

        # Atualizar source_url (cria warning - mudança significativa)
        if dto.source_url is not None:
            old_url = crawler_job.source_url
            new_url = str(dto.source_url)
            crawler_job.source_url = new_url
            updated_fields.append("source_url")
            warnings.append(
                f"URL changed from '{old_url}' to '{new_url}'. "
                "This creates a new crawler target. Consider creating a new job instead."
            )

        # Atualizar config
        if dto.config is not None:
            self._update_config(crawler_job, dto.config, updated_fields)

        # Atualizar schedule
        if dto.schedule is not None:
            self._update_schedule(crawler_job, dto.schedule, updated_fields, warnings)

        # 5. Atualizar timestamp
        crawler_job.updated_at = datetime.utcnow()

        # 6. Salvar no repositório
        try:
            await self.job_repository.update(crawler_job, user_id)
            logger.info(f"Updated crawler job {job_id} in repository")
        except Exception as e:
            logger.error(f"Failed to update crawler job: {e}")
            raise Exception(f"Failed to update crawler job: {str(e)}")

        # 7. Atualizar índice Elasticsearch
        try:
            es_updates = self._prepare_es_updates(crawler_job, dto)
            if es_updates:
                self.search_adapter.update_crawler_job(job_id, es_updates)
                logger.info(f"Updated crawler job index in Elasticsearch")
        except Exception as e:
            logger.warning(f"Failed to update Elasticsearch index: {e}")
            # Não falhar a atualização se indexação falhar

        # 8. Montar resposta
        return UpdateCrawlerJobResponseDTO(
            job_id=job_id,
            message="Crawler job updated successfully",
            updated_fields=updated_fields,
            warnings=warnings
        )

    def _update_config(
        self,
        crawler_job: CrawlerJob,
        config_dto,
        updated_fields: List[str]
    ) -> None:
        """Aplica mudanças na configuração (partial update)"""
        current_config = crawler_job.config

        # Mode
        if config_dto.mode is not None:
            current_config.mode = CrawlerMode(config_dto.mode)
            updated_fields.append("config.mode")

        # Engine
        if config_dto.engine is not None:
            current_config.engine = CrawlerEngine(config_dto.engine)
            updated_fields.append("config.engine")

        # Depths and limits
        if config_dto.max_depth is not None:
            current_config.max_depth = config_dto.max_depth
            updated_fields.append("config.max_depth")

        if config_dto.max_pages is not None:
            current_config.max_pages = config_dto.max_pages
            updated_fields.append("config.max_pages")

        # Robots.txt
        if config_dto.respect_robots_txt is not None:
            current_config.respect_robots_txt = config_dto.respect_robots_txt
            updated_fields.append("config.respect_robots_txt")

        # External links
        if config_dto.follow_external_links is not None:
            current_config.follow_external_links = config_dto.follow_external_links
            updated_fields.append("config.follow_external_links")

        # Retry config
        if config_dto.max_retries is not None:
            current_config.retry_config.max_retries = config_dto.max_retries
            updated_fields.append("config.max_retries")

        if config_dto.retry_delay_seconds is not None:
            current_config.retry_config.retry_delay_seconds = config_dto.retry_delay_seconds
            updated_fields.append("config.retry_delay_seconds")

        # Asset config
        if config_dto.download_images is not None:
            current_config.asset_config.download_images = config_dto.download_images
            updated_fields.append("config.download_images")

        if config_dto.download_css is not None:
            current_config.asset_config.download_css = config_dto.download_css
            updated_fields.append("config.download_css")

        if config_dto.download_js is not None:
            current_config.asset_config.download_js = config_dto.download_js
            updated_fields.append("config.download_js")

        # Proxy config
        if config_dto.use_proxy is not None or config_dto.proxy_host is not None:
            if config_dto.use_proxy and config_dto.proxy_host and config_dto.proxy_port:
                current_config.proxy_config = ProxyConfig(
                    host=config_dto.proxy_host,
                    port=config_dto.proxy_port,
                    protocol="http",
                    username=config_dto.proxy_username,
                    password=config_dto.proxy_password
                )
                updated_fields.append("config.proxy")
            elif config_dto.use_proxy is False:
                current_config.proxy_config = None
                updated_fields.append("config.proxy")

    def _update_schedule(
        self,
        crawler_job: CrawlerJob,
        schedule_dto,
        updated_fields: List[str],
        warnings: List[str]
    ) -> None:
        """Aplica mudanças no schedule (partial update)"""
        if crawler_job.schedule is None:
            # Criar novo schedule
            crawler_job.schedule = CrawlerSchedule(
                schedule_type=schedule_dto.schedule_type or "one_time",
                cron_expression=schedule_dto.cron_expression,
                timezone=schedule_dto.timezone or "UTC"
            )
            updated_fields.append("schedule")
            warnings.append("Schedule created for job")
        else:
            # Atualizar schedule existente
            if schedule_dto.schedule_type is not None:
                old_type = crawler_job.schedule.schedule_type
                crawler_job.schedule.schedule_type = schedule_dto.schedule_type
                updated_fields.append("schedule.type")

                if old_type == "recurring" and schedule_dto.schedule_type == "one_time":
                    warnings.append("Changed from recurring to one_time: future scheduled executions will be cancelled")

            if schedule_dto.cron_expression is not None:
                crawler_job.schedule.cron_expression = schedule_dto.cron_expression
                updated_fields.append("schedule.cron_expression")
                # Recalcular next_runs
                crawler_job.schedule._calculate_next_runs()
                warnings.append(f"Next execution rescheduled to {crawler_job.schedule.next_runs[0] if crawler_job.schedule.next_runs else 'N/A'}")

            if schedule_dto.timezone is not None:
                crawler_job.schedule.timezone = schedule_dto.timezone
                updated_fields.append("schedule.timezone")

    def _prepare_es_updates(self, crawler_job: CrawlerJob, dto: UpdateCrawlerJobDTO) -> dict:
        """Prepara updates para Elasticsearch"""
        updates = {}

        if dto.source_url is not None:
            from domain.services.url_normalizer_service import URLNormalizerService
            url_str = str(dto.source_url)
            updates["source_url"] = url_str
            updates["normalized_url"] = URLNormalizerService.normalize_url(url_str)
            updates["url_pattern"] = URLNormalizerService.generate_pattern(url_str)
            updates["domain"] = URLNormalizerService.extract_domain(url_str)

        if dto.config:
            if dto.config.mode:
                updates["crawler_mode"] = dto.config.mode
            if dto.config.engine:
                updates["crawler_engine"] = dto.config.engine

        if dto.schedule:
            if dto.schedule.schedule_type:
                updates["schedule_type"] = dto.schedule.schedule_type
            if dto.schedule.cron_expression:
                updates["cron_expression"] = dto.schedule.cron_expression
            if crawler_job.schedule and crawler_job.schedule.next_runs:
                updates["next_run"] = crawler_job.schedule.next_runs[0]

        return updates


class JobNotFoundError(Exception):
    """Job não encontrado"""
    pass


class UnauthorizedError(Exception):
    """Usuário não autorizado"""
    pass


class JobInExecutionError(Exception):
    """Job está em execução e não pode ser alterado"""
    pass
