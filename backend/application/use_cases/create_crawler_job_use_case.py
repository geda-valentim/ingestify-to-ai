"""
Create Crawler Job Use Case - Creates new crawler job

Use case para criar novo crawler job com validações e detecção de duplicatas.
"""
import logging
import uuid
from datetime import datetime
from typing import List

from domain.entities.crawler_job import CrawlerJob, CrawlerJobStatus
from domain.value_objects.crawler_config import CrawlerConfig
from domain.value_objects.crawler_schedule import CrawlerSchedule
from domain.repositories.crawler_job_repository import CrawlerJobRepository
from domain.services.url_normalizer_service import URLNormalizerService
from application.ports.crawler_search_port import CrawlerSearchPort
from application.dto.create_crawler_job_dto import CreateCrawlerJobDTO, CreateCrawlerJobResponseDTO
from application.dto.duplicate_warning_dto import DuplicateJobDTO

logger = logging.getLogger(__name__)


class CreateCrawlerJobUseCase:
    """
    Use Case: Criar Crawler Job

    Responsabilidades:
    - Validar URL e configurações
    - Detectar jobs duplicados/similares
    - Criar entidade CrawlerJob
    - Persistir no repositório
    - Indexar no Elasticsearch
    - Retornar avisos sobre duplicatas
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
        dto: CreateCrawlerJobDTO,
        user_id: str
    ) -> CreateCrawlerJobResponseDTO:
        """
        Cria novo crawler job.

        Args:
            dto: Dados do job a criar
            user_id: ID do usuário criador

        Returns:
            CreateCrawlerJobResponseDTO com job_id e avisos

        Raises:
            ValueError: Se URL inválida ou configuração inválida
            Exception: Erros de persistência
        """
        logger.info(f"Creating crawler job for user {user_id}, URL: {dto.source_url}")

        # 1. Validar URL
        url_str = str(dto.source_url)
        if not URLNormalizerService.validate_url(url_str, allow_localhost=False):
            raise ValueError(f"Invalid URL for crawling: {url_str}")

        normalized_url = URLNormalizerService.normalize_url(url_str)
        url_pattern = URLNormalizerService.generate_pattern(url_str)
        domain = URLNormalizerService.extract_domain(url_str)

        logger.debug(f"URL normalized: {normalized_url}, pattern: {url_pattern}")

        # 2. Detectar duplicatas/similares
        warnings = await self._check_duplicates(
            url_pattern=url_pattern,
            normalized_url=normalized_url,
            domain=domain,
            user_id=user_id
        )

        # 3. Criar value objects
        config = self._create_config(dto.config)
        schedule = self._create_schedule(dto.schedule) if dto.schedule else None

        # 4. Criar entidade CrawlerJob
        job_id = str(uuid.uuid4())
        crawler_job = CrawlerJob(
            id=job_id,
            name=dto.name,
            source_url=url_str,
            config=config,
            schedule=schedule,
            status=CrawlerJobStatus.ACTIVE,
            total_executions=0,
            successful_executions=0,
            failed_executions=0,
            last_execution=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        logger.info(f"Created CrawlerJob entity: {job_id}")

        # 5. Salvar no repositório
        try:
            await self.job_repository.save(crawler_job, user_id)
            logger.info(f"Saved CrawlerJob to repository: {job_id}")
        except Exception as e:
            logger.error(f"Failed to save CrawlerJob: {e}")
            raise Exception(f"Failed to create crawler job: {str(e)}")

        # 6. Indexar no Elasticsearch
        try:
            indexed = self.search_adapter.index_crawler_job(
                job_id=job_id,
                user_id=user_id,
                source_url=url_str,
                normalized_url=normalized_url,
                url_pattern=url_pattern,
                domain=domain,
                status=crawler_job.status.value,
                crawler_mode=config.mode.value,
                crawler_engine=config.engine.value,
                schedule_type=schedule.schedule_type if schedule else None,
                cron_expression=schedule.cron_expression if schedule else None,
                next_run=schedule.next_runs[0] if schedule and schedule.next_runs else None,
                last_execution=None,
                total_executions=0,
                created_at=crawler_job.created_at,
                updated_at=crawler_job.updated_at
            )

            if indexed:
                logger.info(f"Indexed CrawlerJob in Elasticsearch: {job_id}")
            else:
                logger.warning(f"Failed to index CrawlerJob in Elasticsearch: {job_id}")

        except Exception as e:
            logger.error(f"Failed to index crawler job: {e}")
            # Não falhar a criação se indexação falhar (é apenas uma projeção)

        # 7. Montar resposta
        return CreateCrawlerJobResponseDTO(
            job_id=job_id,
            name=dto.name,
            source_url=url_str,
            status=crawler_job.status.value,
            message="Crawler job created successfully",
            warnings=warnings
        )

    async def _check_duplicates(
        self,
        url_pattern: str,
        normalized_url: str,
        domain: str,
        user_id: str
    ) -> List[str]:
        """
        Verifica jobs duplicados/similares.

        Returns:
            Lista de mensagens de aviso
        """
        warnings = []

        try:
            # Buscar jobs similares (mesmo padrão)
            similar_jobs = self.search_adapter.find_similar_jobs(
                url_pattern=url_pattern,
                user_id=user_id
            )

            if similar_jobs:
                for job in similar_jobs[:3]:  # Máximo 3 avisos
                    warnings.append(
                        f"Similar crawler job found: '{job.get('name', 'Unknown')}' "
                        f"(job_id: {job['job_id']}, status: {job['status']})"
                    )

            # Buscar por URL exata normalizada
            exact_matches = self.search_adapter.search_by_url(
                url_query=normalized_url,
                user_id=user_id,
                limit=1
            )

            if exact_matches:
                job = exact_matches[0]
                if job.get('normalized_url') == normalized_url:
                    warnings.insert(0,
                        f"Exact duplicate found: '{job.get('name', 'Unknown')}' "
                        f"(job_id: {job['job_id']}, status: {job['status']}). "
                        f"Consider reusing existing crawler instead."
                    )

        except Exception as e:
            logger.warning(f"Failed to check duplicates: {e}")
            # Não falhar a criação se busca de duplicatas falhar

        return warnings

    def _create_config(self, config_dto) -> CrawlerConfig:
        """Cria CrawlerConfig a partir do DTO"""
        from domain.value_objects.crawler_enums import CrawlerMode, CrawlerEngine
        from domain.value_objects.crawler_config import RetryConfig, AssetConfig
        from domain.value_objects.proxy_config import ProxyConfig

        retry_config = RetryConfig(
            max_retries=config_dto.max_retries,
            retry_delay_seconds=config_dto.retry_delay_seconds
        )

        asset_config = AssetConfig(
            download_images=config_dto.download_images,
            download_css=config_dto.download_css,
            download_js=config_dto.download_js
        )

        proxy_config = None
        if config_dto.use_proxy and config_dto.proxy_host and config_dto.proxy_port:
            proxy_config = ProxyConfig(
                host=config_dto.proxy_host,
                port=config_dto.proxy_port,
                protocol="http",  # Default
                username=config_dto.proxy_username,
                password=config_dto.proxy_password
            )

        return CrawlerConfig(
            mode=CrawlerMode(config_dto.mode),
            engine=CrawlerEngine(config_dto.engine),
            max_depth=config_dto.max_depth,
            max_pages=config_dto.max_pages,
            respect_robots_txt=config_dto.respect_robots_txt,
            follow_external_links=config_dto.follow_external_links,
            retry_config=retry_config,
            asset_config=asset_config,
            proxy_config=proxy_config
        )

    def _create_schedule(self, schedule_dto) -> CrawlerSchedule:
        """Cria CrawlerSchedule a partir do DTO"""
        return CrawlerSchedule(
            schedule_type=schedule_dto.schedule_type,
            cron_expression=schedule_dto.cron_expression,
            timezone=schedule_dto.timezone
        )


class JobCreationError(Exception):
    """Erro durante criação de job"""
    pass


class DuplicateJobError(Exception):
    """Job duplicado encontrado"""
    pass
