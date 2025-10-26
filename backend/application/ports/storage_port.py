"""
Storage Port - Interface for result storage

Abstração para armazenamento de resultados (Redis, Elasticsearch, S3, etc.)
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class StoragePort(ABC):
    """
    Interface para armazenamento de resultados

    Pode ser implementado com Redis, Elasticsearch, S3, etc.
    """

    @abstractmethod
    async def store_job_result(
        self,
        job_id: str,
        markdown: str,
        metadata: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Armazena resultado de um job

        Args:
            job_id: Job ID
            markdown: Conteúdo markdown
            metadata: Metadata do documento
            ttl_seconds: Time-to-live em segundos (opcional)

        Returns:
            True se armazenado com sucesso
        """
        pass

    @abstractmethod
    async def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera resultado de um job

        Args:
            job_id: Job ID

        Returns:
            Dict com markdown e metadata, ou None se não encontrado
        """
        pass

    @abstractmethod
    async def store_page_result(
        self,
        job_id: str,
        page_number: int,
        markdown: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Armazena resultado de uma página

        Args:
            job_id: Main job ID
            page_number: Page number
            markdown: Conteúdo markdown
            metadata: Metadata da página

        Returns:
            True se armazenado
        """
        pass

    @abstractmethod
    async def get_page_result(
        self,
        job_id: str,
        page_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Recupera resultado de uma página

        Args:
            job_id: Main job ID
            page_number: Page number

        Returns:
            Dict com markdown e metadata, ou None
        """
        pass

    @abstractmethod
    async def delete_job_result(self, job_id: str) -> bool:
        """
        Deleta resultado de um job

        Args:
            job_id: Job ID

        Returns:
            True se deletado
        """
        pass

    @abstractmethod
    async def search_jobs(
        self,
        query: str,
        user_id: str,
        limit: int = 10
    ) -> list:
        """
        Busca jobs por conteúdo

        Args:
            query: Search query
            user_id: User ID (filter)
            limit: Max results

        Returns:
            Lista de resultados
        """
        pass
