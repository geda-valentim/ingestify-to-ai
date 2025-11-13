"""
Elasticsearch Crawler Index Adapter

Implementa CrawlerSearchPort usando Elasticsearch.
Indexa crawler jobs para busca rápida e detecção de duplicatas.
"""
from typing import List, Optional
from datetime import datetime

from application.ports.crawler_search_port import CrawlerSearchPort
from shared.elasticsearch_client import ElasticsearchClient


class ElasticsearchCrawlerIndex(CrawlerSearchPort):
    """
    Adapter para indexação de crawler jobs no Elasticsearch.

    Responsabilidades:
    - Indexar jobs para busca fuzzy por URL
    - Detectar jobs duplicados/similares
    - Buscar jobs por domínio
    - Manter sincronização com MySQL (projection/view)
    """

    def __init__(self, es_client: ElasticsearchClient):
        """
        Args:
            es_client: Cliente Elasticsearch
        """
        self.es_client = es_client

    def index_crawler_job(
        self,
        job_id: str,
        user_id: str,
        source_url: str,
        normalized_url: str,
        url_pattern: str,
        domain: str,
        status: str,
        crawler_mode: str,
        crawler_engine: str,
        schedule_type: Optional[str] = None,
        cron_expression: Optional[str] = None,
        next_run: Optional[datetime] = None,
        last_execution: Optional[datetime] = None,
        total_executions: int = 0,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ) -> bool:
        """
        Indexa crawler job no Elasticsearch.

        Args:
            job_id: ID do job
            user_id: ID do usuário
            source_url: URL original
            normalized_url: URL normalizada
            url_pattern: Padrão da URL para fuzzy matching
            domain: Domínio extraído
            status: Status do job
            crawler_mode: Modo do crawler
            crawler_engine: Engine usado
            schedule_type: Tipo de agendamento
            cron_expression: Expressão cron
            next_run: Próxima execução
            last_execution: Última execução
            total_executions: Total de execuções
            created_at: Data de criação
            updated_at: Data de atualização

        Returns:
            True se indexado com sucesso
        """
        return self.es_client.store_crawler_job(
            job_id=job_id,
            user_id=user_id,
            source_url=source_url,
            normalized_url=normalized_url,
            url_pattern=url_pattern,
            domain=domain,
            status=status,
            crawler_mode=crawler_mode,
            crawler_engine=crawler_engine,
            schedule_type=schedule_type,
            cron_expression=cron_expression,
            next_run=next_run,
            last_execution=last_execution,
            total_executions=total_executions,
            created_at=created_at,
            updated_at=updated_at
        )

    def update_crawler_job(self, job_id: str, updates: dict) -> bool:
        """
        Atualiza campos de um crawler job indexado.

        Args:
            job_id: ID do job
            updates: Campos a atualizar (ex: {"status": "paused"})

        Returns:
            True se atualizado com sucesso

        Example:
            >>> adapter.update_crawler_job("job-123", {
            ...     "status": "paused",
            ...     "last_execution": datetime.utcnow()
            ... })
        """
        return self.es_client.update_crawler_job(job_id, updates)

    def delete_crawler_job(self, job_id: str) -> bool:
        """
        Remove crawler job do índice.

        Args:
            job_id: ID do job

        Returns:
            True se deletado com sucesso
        """
        return self.es_client.delete_crawler_job(job_id)

    def get_crawler_job(self, job_id: str) -> Optional[dict]:
        """
        Busca crawler job por ID.

        Args:
            job_id: ID do job

        Returns:
            Dados do job ou None
        """
        return self.es_client.get_crawler_job(job_id)

    def search_by_url(
        self,
        url_query: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[dict]:
        """
        Busca jobs por URL (fuzzy matching).

        Busca em:
        - source_url (texto completo)
        - normalized_url (exato)
        - domain (exato)

        Args:
            url_query: URL ou parte da URL
            user_id: Filtrar por usuário
            limit: Máximo de resultados

        Returns:
            Lista de jobs encontrados

        Example:
            >>> jobs = adapter.search_by_url("example.com")
            >>> for job in jobs:
            ...     print(job["source_url"])
        """
        return self.es_client.search_crawler_jobs_by_url(
            url_query=url_query,
            user_id=user_id,
            limit=limit
        )

    def find_similar_jobs(
        self,
        url_pattern: str,
        user_id: str,
        exclude_job_id: Optional[str] = None
    ) -> List[dict]:
        """
        Encontra jobs com mesmo padrão de URL (detecção de duplicatas).

        Útil para:
        - Detectar crawlers duplicados antes de criar
        - Avisar usuário sobre jobs similares existentes
        - Consolidar jobs com mesmo padrão

        Args:
            url_pattern: Padrão da URL (ex: "https://example.com/page?id=*")
            user_id: ID do usuário
            exclude_job_id: Excluir este job dos resultados

        Returns:
            Lista de jobs similares

        Example:
            >>> pattern = "https://example.com/page?id=*"
            >>> similar = adapter.find_similar_jobs(pattern, "user-123")
            >>> if similar:
            ...     print(f"Found {len(similar)} similar jobs")
        """
        return self.es_client.find_similar_crawler_jobs(
            url_pattern=url_pattern,
            user_id=user_id,
            exclude_job_id=exclude_job_id
        )

    def find_by_domain(
        self,
        domain: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[dict]:
        """
        Busca jobs por domínio.

        Útil para:
        - Ver todos os crawlers de um domínio
        - Aplicar políticas por domínio (rate limiting)
        - Analytics por domínio

        Args:
            domain: Domínio a buscar (ex: "example.com")
            user_id: Filtrar por usuário
            limit: Máximo de resultados

        Returns:
            Lista de jobs do domínio

        Example:
            >>> jobs = adapter.find_by_domain("example.com", user_id="user-123")
            >>> print(f"User has {len(jobs)} crawlers for example.com")
        """
        return self.es_client.find_crawler_jobs_by_domain(
            domain=domain,
            user_id=user_id,
            limit=limit
        )

    def health_check(self) -> bool:
        """
        Verifica se Elasticsearch está saudável.

        Returns:
            True se saudável
        """
        return self.es_client.health_check()

    # === Utility Methods ===

    def index_from_crawler_job(self, crawler_job, user_id: str) -> bool:
        """
        Indexa a partir de uma CrawlerJob entity.

        Helper method para facilitar indexação de entities do domínio.

        Args:
            crawler_job: CrawlerJob entity
            user_id: ID do usuário

        Returns:
            True se indexado com sucesso

        Example:
            >>> from domain.entities.crawler_job import CrawlerJob
            >>> crawler_job = CrawlerJob(...)
            >>> adapter.index_from_crawler_job(crawler_job, "user-123")
        """
        from domain.services.url_normalizer_service import URLNormalizerService

        # Normalizar URL
        normalized_url = URLNormalizerService.normalize_url(crawler_job.source_url)
        url_pattern = URLNormalizerService.generate_pattern(crawler_job.source_url)
        domain = URLNormalizerService.extract_domain(crawler_job.source_url)

        # Extrair dados de schedule
        schedule_type = None
        cron_expression = None
        next_run = None

        if crawler_job.schedule:
            schedule_type = crawler_job.schedule.schedule_type
            cron_expression = crawler_job.schedule.cron_expression
            # Next run pode ser calculado pela schedule
            if hasattr(crawler_job.schedule, 'next_runs') and crawler_job.schedule.next_runs:
                next_run = crawler_job.schedule.next_runs[0]

        return self.index_crawler_job(
            job_id=crawler_job.id,
            user_id=user_id,
            source_url=crawler_job.source_url,
            normalized_url=normalized_url,
            url_pattern=url_pattern,
            domain=domain,
            status=crawler_job.status.value,
            crawler_mode=crawler_job.config.mode.value,
            crawler_engine=crawler_job.config.engine.value,
            schedule_type=schedule_type,
            cron_expression=cron_expression,
            next_run=next_run,
            last_execution=crawler_job.last_execution,
            total_executions=crawler_job.total_executions,
            created_at=crawler_job.created_at,
            updated_at=crawler_job.updated_at
        )
