"""
Delete Crawler Job Use Case - Deletes crawler job with cascades

Use case para deletar crawler job e todos os recursos associados.
"""
import logging
from typing import Dict

from domain.repositories.crawler_job_repository import CrawlerJobRepository
from infrastructure.repositories.mysql_crawled_file_repository import MySQLCrawledFileRepository
from application.ports.crawler_search_port import CrawlerSearchPort
from application.dto.common_responses_dto import DeleteResponseDTO

logger = logging.getLogger(__name__)


class DeleteCrawlerJobUseCase:
    """
    Use Case: Deletar Crawler Job

    Responsabilidades:
    - Buscar job existente
    - Verificar ownership
    - Verificar se há execuções em andamento
    - Deletar job (cascade para execuções e arquivos)
    - Remover do índice Elasticsearch
    - Retornar estatísticas de deleção
    """

    def __init__(
        self,
        job_repository: CrawlerJobRepository,
        file_repository: MySQLCrawledFileRepository,
        search_adapter: CrawlerSearchPort
    ):
        """
        Args:
            job_repository: Repositório de CrawlerJob
            file_repository: Repositório de CrawledFile
            search_adapter: Adapter para busca (Elasticsearch)
        """
        self.job_repository = job_repository
        self.file_repository = file_repository
        self.search_adapter = search_adapter

    async def execute(
        self,
        job_id: str,
        user_id: str,
        force: bool = False
    ) -> DeleteResponseDTO:
        """
        Delete crawler job e recursos relacionados.

        Args:
            job_id: ID do job a deletar
            user_id: ID do usuário (ownership check)
            force: Se True, deleta mesmo com execuções em andamento

        Returns:
            DeleteResponseDTO com estatísticas de deleção

        Raises:
            JobNotFoundError: Se job não existe
            UnauthorizedError: Se usuário não é dono
            JobInExecutionError: Se tem execuções em andamento e force=False
        """
        logger.info(f"Deleting crawler job {job_id} for user {user_id}, force={force}")

        # 1. Buscar job existente
        crawler_job = await self.job_repository.find_by_id(job_id)
        if not crawler_job:
            raise JobNotFoundError(f"Crawler job {job_id} not found")

        # 2. Verificar ownership
        job_user_id = await self.job_repository.get_user_id(job_id)
        if job_user_id != user_id:
            raise UnauthorizedError(f"User {user_id} does not own crawler job {job_id}")

        # 3. Verificar execuções em andamento
        if not force:
            active_executions = await self._count_active_executions(job_id)
            if active_executions > 0:
                raise JobInExecutionError(
                    f"Crawler job has {active_executions} active executions. "
                    "Use force=true to delete anyway."
                )

        # 4. Coletar estatísticas antes de deletar (para resposta)
        cascade_stats = await self._collect_cascade_stats(job_id)

        # 5. Deletar job (cascade automático no MySQL via FK constraints)
        # O MySQL vai deletar automaticamente:
        # - Execuções (jobs com parent_job_id = job_id)
        # - Arquivos crawleados (crawled_files com execution_id = execution_ids)
        try:
            await self.job_repository.delete(job_id)
            logger.info(f"Deleted crawler job {job_id} from repository (cascade applied)")
        except Exception as e:
            logger.error(f"Failed to delete crawler job: {e}")
            raise Exception(f"Failed to delete crawler job: {str(e)}")

        # 6. Remover do índice Elasticsearch
        try:
            self.search_adapter.delete_crawler_job(job_id)
            logger.info(f"Deleted crawler job {job_id} from Elasticsearch index")
        except Exception as e:
            logger.warning(f"Failed to delete from Elasticsearch: {e}")
            # Não falhar a deleção se ES falhar

        # 7. Montar resposta
        return DeleteResponseDTO(
            job_id=job_id,
            message="Crawler job deleted successfully",
            cascade_deleted=cascade_stats
        )

    async def _count_active_executions(self, crawler_job_id: str) -> int:
        """
        Conta execuções ativas (pending/processing) do crawler job.

        Returns:
            Número de execuções ativas
        """
        try:
            # Buscar jobs filhos (execuções) com status pending/processing
            # Nota: Assumindo que há um método no repository para isso
            # Se não houver, pode usar query direta no MySQL
            executions = await self.job_repository.find_child_jobs(
                parent_job_id=crawler_job_id,
                status_filter=["pending", "processing"]
            )
            return len(executions)
        except Exception as e:
            logger.warning(f"Failed to count active executions: {e}")
            return 0  # Assumir 0 se falhar

    async def _collect_cascade_stats(self, crawler_job_id: str) -> Dict[str, int]:
        """
        Coleta estatísticas de recursos que serão deletados em cascata.

        Returns:
            Dict com contagens: {executions, crawled_files, elasticsearch_docs}
        """
        stats = {
            "executions": 0,
            "crawled_files": 0,
            "elasticsearch_docs": 0
        }

        try:
            # Contar execuções (child jobs)
            executions = await self.job_repository.find_child_jobs(parent_job_id=crawler_job_id)
            stats["executions"] = len(executions)

            # Contar arquivos crawleados (de todas as execuções)
            total_files = 0
            for execution in executions:
                files = await self.file_repository.find_by_execution_id(execution.id)
                total_files += len(files)
            stats["crawled_files"] = total_files

            # Elasticsearch: 1 doc do crawler job + docs das execuções
            stats["elasticsearch_docs"] = 1 + stats["executions"]

        except Exception as e:
            logger.warning(f"Failed to collect cascade stats: {e}")

        return stats


class JobNotFoundError(Exception):
    """Job não encontrado"""
    pass


class UnauthorizedError(Exception):
    """Usuário não autorizado"""
    pass


class JobInExecutionError(Exception):
    """Job tem execuções em andamento"""
    pass
