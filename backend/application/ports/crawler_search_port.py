"""
Crawler Search Port - Interface for crawler job indexing and search

Port (interface) para busca e indexação de crawler jobs.
Permite busca fuzzy por URL e detecção de duplicatas.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime


class CrawlerSearchPort(ABC):
    """
    Port para indexação e busca de crawler jobs.

    Permite:
    - Indexar jobs para busca rápida
    - Busca fuzzy por URL
    - Detecção de jobs similares (duplicatas)
    - Busca por domínio
    """

    @abstractmethod
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
        Indexa crawler job para busca.

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
        pass

    @abstractmethod
    def update_crawler_job(self, job_id: str, updates: dict) -> bool:
        """
        Atualiza campos de um crawler job indexado.

        Args:
            job_id: ID do job
            updates: Campos a atualizar

        Returns:
            True se atualizado com sucesso
        """
        pass

    @abstractmethod
    def delete_crawler_job(self, job_id: str) -> bool:
        """
        Remove crawler job do índice.

        Args:
            job_id: ID do job

        Returns:
            True se deletado com sucesso
        """
        pass

    @abstractmethod
    def get_crawler_job(self, job_id: str) -> Optional[dict]:
        """
        Busca crawler job por ID.

        Args:
            job_id: ID do job

        Returns:
            Dados do job ou None
        """
        pass

    @abstractmethod
    def search_by_url(
        self,
        url_query: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[dict]:
        """
        Busca jobs por URL (fuzzy matching).

        Args:
            url_query: URL ou parte da URL
            user_id: Filtrar por usuário
            limit: Máximo de resultados

        Returns:
            Lista de jobs encontrados
        """
        pass

    @abstractmethod
    def find_similar_jobs(
        self,
        url_pattern: str,
        user_id: str,
        exclude_job_id: Optional[str] = None
    ) -> List[dict]:
        """
        Encontra jobs com mesmo padrão de URL (detecção de duplicatas).

        Args:
            url_pattern: Padrão da URL
            user_id: ID do usuário
            exclude_job_id: Excluir este job dos resultados

        Returns:
            Lista de jobs similares
        """
        pass

    @abstractmethod
    def find_by_domain(
        self,
        domain: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[dict]:
        """
        Busca jobs por domínio.

        Args:
            domain: Domínio a buscar
            user_id: Filtrar por usuário
            limit: Máximo de resultados

        Returns:
            Lista de jobs do domínio
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Verifica se o serviço de busca está saudável.

        Returns:
            True se saudável
        """
        pass
