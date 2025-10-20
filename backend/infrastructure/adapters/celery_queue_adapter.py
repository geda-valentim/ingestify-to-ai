"""
Celery Queue Adapter - Implementa QueuePort

Adapta Celery para a interface QueuePort definida na Application layer
"""
import logging
from typing import Dict, Any, Optional

from application.ports.queue_port import QueuePort

logger = logging.getLogger(__name__)


class CeleryQueueAdapter(QueuePort):
    """
    Adapter para Celery

    Implementa QueuePort usando Celery como sistema de filas
    """

    def __init__(self):
        """Inicializa adapter"""
        # Import lazy para evitar circular dependency
        pass

    async def enqueue_conversion(
        self,
        job_id: str,
        source_type: str,
        source: str,
        options: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> str:
        """
        Enfileira conversão de documento

        Args:
            job_id: Job ID
            source_type: Tipo de fonte
            source: Fonte do documento
            options: Opções de conversão
            auth_token: Token de autenticação (opcional)

        Returns:
            Task ID
        """
        from workers.tasks import process_conversion

        logger.info(f"Enqueueing conversion job {job_id}")

        task = process_conversion.delay(
            job_id=job_id,
            source_type=source_type,
            source=source,
            options=options,
            auth_token=auth_token
        )

        logger.debug(f"Job {job_id} enqueued with task_id={task.id}")

        return task.id

    async def enqueue_page_conversion(
        self,
        page_job_id: str,
        parent_job_id: str,
        page_number: int,
        page_file_path: str,
        options: Dict[str, Any]
    ) -> str:
        """
        Enfileira conversão de página

        Args:
            page_job_id: Page job ID
            parent_job_id: Parent job ID
            page_number: Page number
            page_file_path: Path to page file
            options: Options

        Returns:
            Task ID
        """
        from workers.tasks import convert_page_task

        logger.info(f"Enqueueing page {page_number} for job {parent_job_id}")

        task = convert_page_task.delay(
            page_job_id=page_job_id,
            parent_job_id=parent_job_id,
            page_number=page_number,
            page_file_path=page_file_path,
            options=options
        )

        logger.debug(f"Page job {page_job_id} enqueued with task_id={task.id}")

        return task.id

    async def enqueue_pdf_split(
        self,
        split_job_id: str,
        parent_job_id: str,
        file_path: str,
        options: Dict[str, Any]
    ) -> str:
        """
        Enfileira split de PDF

        Args:
            split_job_id: Split job ID
            parent_job_id: Parent job ID
            file_path: Path to PDF
            options: Options

        Returns:
            Task ID
        """
        from workers.tasks import split_pdf_task

        logger.info(f"Enqueueing PDF split for job {parent_job_id}")

        task = split_pdf_task.delay(
            split_job_id=split_job_id,
            parent_job_id=parent_job_id,
            file_path=file_path,
            options=options
        )

        logger.debug(f"Split job {split_job_id} enqueued with task_id={task.id}")

        return task.id

    async def enqueue_merge(
        self,
        merge_job_id: str,
        parent_job_id: str
    ) -> str:
        """
        Enfileira merge de páginas

        Args:
            merge_job_id: Merge job ID
            parent_job_id: Parent job ID

        Returns:
            Task ID
        """
        from workers.tasks import merge_pages_task

        logger.info(f"Enqueueing merge for job {parent_job_id}")

        task = merge_pages_task.delay(
            merge_job_id=merge_job_id,
            parent_job_id=parent_job_id
        )

        logger.debug(f"Merge job {merge_job_id} enqueued with task_id={task.id}")

        return task.id

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Consulta status de tarefa

        Args:
            task_id: Task ID

        Returns:
            Status info ou None
        """
        from workers.celery_app import celery_app
        from celery.result import AsyncResult

        task = AsyncResult(task_id, app=celery_app)

        if not task:
            return None

        return {
            "task_id": task_id,
            "status": task.status,
            "result": task.result if task.ready() else None,
        }

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancela tarefa

        Args:
            task_id: Task ID

        Returns:
            True se cancelada
        """
        from workers.celery_app import celery_app
        from celery.result import AsyncResult

        try:
            task = AsyncResult(task_id, app=celery_app)
            task.revoke(terminate=True)
            logger.info(f"Task {task_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return False

    async def get_worker_count(self) -> int:
        """
        Retorna número de workers ativos

        Returns:
            Worker count
        """
        from workers.celery_app import celery_app

        try:
            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            return len(stats) if stats else 0
        except Exception as e:
            logger.warning(f"Failed to get worker count: {e}")
            return 0
