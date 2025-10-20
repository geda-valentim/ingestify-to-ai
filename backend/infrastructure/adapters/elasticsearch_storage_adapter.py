"""
Elasticsearch Storage Adapter - Implementa StoragePort

Adapta Elasticsearch para armazenamento de resultados
"""
import logging
from typing import Optional, Dict, Any

from application.ports.storage_port import StoragePort
from shared.elasticsearch_client import get_es_client

logger = logging.getLogger(__name__)


class ElasticsearchStorageAdapter(StoragePort):
    """
    Adapter para Elasticsearch

    Implementa StoragePort usando Elasticsearch para armazenamento e busca
    """

    def __init__(self):
        """Inicializa adapter"""
        self.es_client = get_es_client()

    async def store_job_result(
        self,
        job_id: str,
        markdown: str,
        metadata: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Armazena resultado de job

        Args:
            job_id: Job ID
            markdown: Markdown content
            metadata: Metadata
            ttl_seconds: TTL (ignorado no ES, usa Redis para TTL)

        Returns:
            True se armazenado
        """
        try:
            success = self.es_client.store_job_result(
                job_id=job_id,
                markdown_content=markdown,
                user_id=metadata.get('user_id'),
                filename=metadata.get('filename'),
                total_pages=metadata.get('pages'),
                metadata=metadata
            )

            if success:
                logger.info(f"Job {job_id} result stored in Elasticsearch")
            else:
                logger.warning(f"Failed to store job {job_id} result in Elasticsearch")

            return success

        except Exception as e:
            logger.error(f"Error storing job {job_id} result: {e}", exc_info=True)
            return False

    async def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera resultado de job

        Args:
            job_id: Job ID

        Returns:
            Dict com markdown e metadata, ou None
        """
        try:
            result = self.es_client.get_job_result(job_id)

            if result:
                return {
                    "markdown": result.get("markdown_content", ""),
                    "metadata": result.get("metadata", {})
                }

            return None

        except Exception as e:
            logger.error(f"Error getting job {job_id} result: {e}")
            return None

    async def store_page_result(
        self,
        job_id: str,
        page_number: int,
        markdown: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Armazena resultado de página

        Args:
            job_id: Main job ID
            page_number: Page number
            markdown: Markdown content
            metadata: Metadata

        Returns:
            True se armazenado
        """
        try:
            success = self.es_client.store_page_result(
                job_id=job_id,
                page_number=page_number,
                markdown_content=markdown,
                metadata=metadata
            )

            if success:
                logger.info(
                    f"Page {page_number} of job {job_id} stored in Elasticsearch"
                )
            else:
                logger.warning(
                    f"Failed to store page {page_number} of job {job_id}"
                )

            return success

        except Exception as e:
            logger.error(
                f"Error storing page {page_number} of job {job_id}: {e}",
                exc_info=True
            )
            return False

    async def get_page_result(
        self,
        job_id: str,
        page_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Recupera resultado de página

        Args:
            job_id: Main job ID
            page_number: Page number

        Returns:
            Dict com markdown e metadata, ou None
        """
        try:
            result = self.es_client.get_page_result(job_id, page_number)

            if result:
                return {
                    "markdown": result.get("markdown_content", ""),
                    "metadata": result.get("metadata", {})
                }

            return None

        except Exception as e:
            logger.error(
                f"Error getting page {page_number} of job {job_id}: {e}"
            )
            return None

    async def delete_job_result(self, job_id: str) -> bool:
        """
        Deleta resultado de job

        Args:
            job_id: Job ID

        Returns:
            True se deletado
        """
        try:
            # Delete main job result
            self.es_client.delete_job_result(job_id)

            # Delete all page results
            self.es_client.delete_all_page_results(job_id)

            logger.info(f"Job {job_id} results deleted from Elasticsearch")
            return True

        except Exception as e:
            logger.error(f"Error deleting job {job_id} results: {e}")
            return False

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
            user_id: User ID
            limit: Max results

        Returns:
            Lista de resultados
        """
        try:
            results = self.es_client.search_jobs(
                query=query,
                user_id=user_id,
                limit=limit
            )

            logger.info(f"Search for '{query}' returned {len(results)} results")

            return results

        except Exception as e:
            logger.error(f"Error searching jobs: {e}")
            return []
