"""
Queue Port - Interface for task queuing

Abstração para sistema de filas (Celery, RabbitMQ, etc.)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class QueuePort(ABC):
    """
    Interface para sistema de filas de tarefas

    Pode ser implementado com Celery, RabbitMQ, Redis Queue, etc.
    """

    @abstractmethod
    async def enqueue_conversion(
        self,
        job_id: str,
        source_type: str,
        source: str,
        options: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> str:
        """
        Enfileira tarefa de conversão

        Args:
            job_id: Job ID
            source_type: Tipo de fonte (file, url, etc.)
            source: Fonte do documento
            options: Opções de conversão
            auth_token: Token de autenticação (opcional)

        Returns:
            Task ID
        """
        pass

    @abstractmethod
    async def enqueue_page_conversion(
        self,
        page_job_id: str,
        parent_job_id: str,
        page_number: int,
        page_file_path: str,
        options: Dict[str, Any]
    ) -> str:
        """
        Enfileira conversão de página individual

        Args:
            page_job_id: Page job ID
            parent_job_id: Parent (main) job ID
            page_number: Page number
            page_file_path: Path to page file
            options: Conversion options

        Returns:
            Task ID
        """
        pass

    @abstractmethod
    async def enqueue_pdf_split(
        self,
        split_job_id: str,
        parent_job_id: str,
        file_path: str,
        options: Dict[str, Any]
    ) -> str:
        """
        Enfileira tarefa de split de PDF

        Args:
            split_job_id: Split job ID
            parent_job_id: Parent (main) job ID
            file_path: Path to PDF file
            options: Options

        Returns:
            Task ID
        """
        pass

    @abstractmethod
    async def enqueue_merge(
        self,
        merge_job_id: str,
        parent_job_id: str
    ) -> str:
        """
        Enfileira tarefa de merge de páginas

        Args:
            merge_job_id: Merge job ID
            parent_job_id: Parent (main) job ID

        Returns:
            Task ID
        """
        pass

    @abstractmethod
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Consulta status de uma tarefa

        Args:
            task_id: Task ID

        Returns:
            Status info ou None
        """
        pass

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancela uma tarefa

        Args:
            task_id: Task ID

        Returns:
            True se cancelada
        """
        pass

    @abstractmethod
    async def get_worker_count(self) -> int:
        """
        Retorna número de workers ativos

        Returns:
            Worker count
        """
        pass
