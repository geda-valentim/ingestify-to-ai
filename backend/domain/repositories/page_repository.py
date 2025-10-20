"""
Page Repository Interface - Abstract Data Access for Pages
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.entities.page import Page, PageStatus


class PageRepository(ABC):
    """
    Interface abstrata para repositório de Pages

    Gerencia páginas individuais de PDFs
    """

    @abstractmethod
    async def save(self, page: Page) -> None:
        """
        Salva ou atualiza uma página

        Args:
            page: Page entity to save
        """
        pass

    @abstractmethod
    async def find_by_id(self, page_id: str) -> Optional[Page]:
        """
        Busca página por ID

        Args:
            page_id: Page ID

        Returns:
            Page entity ou None
        """
        pass

    @abstractmethod
    async def find_by_job_id(self, job_id: str) -> List[Page]:
        """
        Busca todas as páginas de um job

        Args:
            job_id: Job ID

        Returns:
            Lista de páginas ordenadas por page_number
        """
        pass

    @abstractmethod
    async def find_by_job_and_number(self, job_id: str, page_number: int) -> Optional[Page]:
        """
        Busca página específica por job e número

        Args:
            job_id: Job ID
            page_number: Page number (1-indexed)

        Returns:
            Page entity ou None
        """
        pass

    @abstractmethod
    async def count_by_status(self, job_id: str, status: PageStatus) -> int:
        """
        Conta páginas de um job com determinado status

        Args:
            job_id: Job ID
            status: Page status

        Returns:
            Count
        """
        pass

    @abstractmethod
    async def update_status(self, page_id: str, status: PageStatus) -> bool:
        """
        Atualiza status de uma página

        Args:
            page_id: Page ID
            status: New status

        Returns:
            True se atualizado
        """
        pass

    @abstractmethod
    async def delete_by_job_id(self, job_id: str) -> int:
        """
        Deleta todas as páginas de um job

        Args:
            job_id: Job ID

        Returns:
            Número de páginas deletadas
        """
        pass
