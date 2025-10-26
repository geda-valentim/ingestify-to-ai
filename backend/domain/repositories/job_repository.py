"""
Job Repository Interface - Abstract Data Access

Define o contrato para persistência de Jobs
Implementações concretas ficam na camada de Infraestrutura
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.entities.job import Job, JobStatus, JobType


class JobRepository(ABC):
    """
    Interface abstrata para repositório de Jobs

    Implementações podem usar MySQL, Redis, Elasticsearch, etc.
    """

    @abstractmethod
    async def save(self, job: Job) -> None:
        """
        Salva ou atualiza um job

        Args:
            job: Job entity to save
        """
        pass

    @abstractmethod
    async def find_by_id(self, job_id: str) -> Optional[Job]:
        """
        Busca job por ID

        Args:
            job_id: Job ID

        Returns:
            Job entity ou None se não encontrado
        """
        pass

    @abstractmethod
    async def find_by_user_id(
        self,
        user_id: str,
        job_type: Optional[JobType] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Job]:
        """
        Busca jobs por user_id com filtros opcionais

        Args:
            user_id: User ID
            job_type: Filtrar por tipo (opcional)
            status: Filtrar por status (opcional)
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Lista de jobs
        """
        pass

    @abstractmethod
    async def find_child_jobs(self, parent_job_id: str) -> List[Job]:
        """
        Busca todos os child jobs de um parent

        Args:
            parent_job_id: Parent job ID

        Returns:
            Lista de child jobs
        """
        pass

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """
        Deleta um job

        Args:
            job_id: Job ID

        Returns:
            True se deletado com sucesso
        """
        pass

    @abstractmethod
    async def update_progress(self, job_id: str, progress: int) -> bool:
        """
        Atualiza progresso de um job

        Args:
            job_id: Job ID
            progress: Progress value (0-100)

        Returns:
            True se atualizado com sucesso
        """
        pass

    @abstractmethod
    async def update_status(self, job_id: str, status: JobStatus) -> bool:
        """
        Atualiza status de um job

        Args:
            job_id: Job ID
            status: New status

        Returns:
            True se atualizado com sucesso
        """
        pass

    @abstractmethod
    async def count_by_user(self, user_id: str) -> int:
        """
        Conta total de jobs de um usuário

        Args:
            user_id: User ID

        Returns:
            Total count
        """
        pass

    @abstractmethod
    async def exists(self, job_id: str) -> bool:
        """
        Verifica se job existe

        Args:
            job_id: Job ID

        Returns:
            True se existe
        """
        pass
