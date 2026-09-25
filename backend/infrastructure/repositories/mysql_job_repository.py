"""
MySQL Job Repository - Concrete implementation using SQLAlchemy

Implementa JobRepository interface usando MySQL como persistência
"""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from domain.entities.job import Job, JobStatus, JobType
from domain.entities.crawler_job import CrawlerJob
from domain.value_objects.crawler_config import CrawlerConfig
from domain.value_objects.crawler_schedule import CrawlerSchedule
from domain.repositories.job_repository import JobRepository
from shared.models import Job as JobModel, JobStatus as DBJobStatus
from shared.database import SessionLocal

logger = logging.getLogger(__name__)


class MySQLJobRepository(JobRepository):
    """
    Implementação concreta de JobRepository usando MySQL (SQLAlchemy)

    Converte entre Domain Entities e ORM Models
    """

    def __init__(self, session: Optional[Session] = None):
        """
        Inicializa repository

        Args:
            session: SQLAlchemy session (opcional, cria nova se não fornecido)
        """
        self.session = session or SessionLocal()

    async def save(self, job: Job) -> None:
        """
        Salva ou atualiza job

        Args:
            job: Job entity
        """
        # Buscar se já existe
        db_job = self.session.query(JobModel).filter(JobModel.id == job.id).first()

        if db_job:
            # Update existing
            self._update_model_from_entity(db_job, job)
        else:
            # Create new
            db_job = self._entity_to_model(job)
            self.session.add(db_job)

        try:
            self.session.commit()
            logger.debug(f"Job {job.id} saved to MySQL")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to save job {job.id}: {e}", exc_info=True)
            raise

    async def find_by_id(self, job_id: str) -> Optional[Job]:
        """
        Busca job por ID

        Args:
            job_id: Job ID

        Returns:
            Job entity ou None
        """
        db_job = self.session.query(JobModel).filter(JobModel.id == job_id).first()

        if not db_job:
            return None

        return self._model_to_entity(db_job)

    async def find_by_user_id(
        self,
        user_id: str,
        job_type: Optional[JobType] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Job]:
        """
        Busca jobs por user_id com filtros

        Args:
            user_id: User ID
            job_type: Filtrar por tipo (opcional)
            status: Filtrar por status (opcional)
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Lista de jobs
        """
        query = self.session.query(JobModel).filter(JobModel.user_id == user_id)

        # Aplicar filtros
        if job_type:
            query = query.filter(JobModel.job_type == job_type.value)

        if status:
            query = query.filter(JobModel.status == self._status_to_db_status(status))

        # Ordenar por criação (mais recente primeiro)
        query = query.order_by(JobModel.created_at.desc())

        # Paginação
        query = query.limit(limit).offset(offset)

        db_jobs = query.all()

        return [self._model_to_entity(db_job) for db_job in db_jobs]

    async def find_child_jobs(self, parent_job_id: str) -> List[Job]:
        """
        Busca child jobs

        Args:
            parent_job_id: Parent job ID

        Returns:
            Lista de child jobs
        """
        db_jobs = self.session.query(JobModel).filter(
            JobModel.parent_job_id == parent_job_id
        ).all()

        return [self._model_to_entity(db_job) for db_job in db_jobs]

    async def delete(self, job_id: str) -> bool:
        """
        Deleta job

        Args:
            job_id: Job ID

        Returns:
            True se deletado
        """
        try:
            deleted = self.session.query(JobModel).filter(
                JobModel.id == job_id
            ).delete()

            self.session.commit()
            return deleted > 0
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to delete job {job_id}: {e}", exc_info=True)
            return False

    async def update_progress(self, job_id: str, progress: int) -> bool:
        """
        Atualiza progresso

        Args:
            job_id: Job ID
            progress: Progress (0-100)

        Returns:
            True se atualizado
        """
        try:
            updated = self.session.query(JobModel).filter(
                JobModel.id == job_id
            ).update({"progress": progress})

            self.session.commit()
            return updated > 0
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to update progress for job {job_id}: {e}")
            return False

    async def update_status(self, job_id: str, status: JobStatus) -> bool:
        """
        Atualiza status

        Args:
            job_id: Job ID
            status: New status

        Returns:
            True se atualizado
        """
        try:
            updated = self.session.query(JobModel).filter(
                JobModel.id == job_id
            ).update({"status": self._status_to_db_status(status)})

            self.session.commit()
            return updated > 0
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to update status for job {job_id}: {e}")
            return False

    async def count_by_user(self, user_id: str) -> int:
        """
        Conta jobs de usuário

        Args:
            user_id: User ID

        Returns:
            Total count
        """
        return self.session.query(JobModel).filter(
            JobModel.user_id == user_id
        ).count()

    async def exists(self, job_id: str) -> bool:
        """
        Verifica se job existe

        Args:
            job_id: Job ID

        Returns:
            True se existe
        """
        return self.session.query(JobModel).filter(
            JobModel.id == job_id
        ).count() > 0

    # ============================================
    # Métodos Específicos para Crawler (STI)
    # ============================================

    async def find_crawler_jobs(
        self,
        user_id: str,
        filters: Optional[dict] = None
    ) -> List[CrawlerJob]:
        """
        Busca crawler jobs com filtros opcionais.

        Args:
            user_id: User ID
            filters: Filtros opcionais (status, search, etc.)

        Returns:
            Lista de CrawlerJob entities
        """
        query = self.session.query(JobModel).filter(
            JobModel.user_id == user_id,
            JobModel.job_type == "crawler"
        )

        # Apply filters if provided
        if filters:
            if "status" in filters:
                query = query.filter(JobModel.status == self._status_to_db_status(filters["status"]))

            if "search" in filters and filters["search"]:
                search_term = f"%{filters['search']}%"
                query = query.filter(JobModel.source_url.like(search_term))

        # Order by creation (most recent first)
        query = query.order_by(JobModel.created_at.desc())

        db_jobs = query.all()

        return [self._model_to_crawler_job(db_job) for db_job in db_jobs]

    async def find_active_crawlers(self) -> List[CrawlerJob]:
        """
        Busca crawlers ativos (para scheduler Celery Beat).

        Crawlers ativos são aqueles com status PENDING ou QUEUED.

        Returns:
            Lista de CrawlerJob entities ativos
        """
        db_jobs = self.session.query(JobModel).filter(
            JobModel.job_type == "crawler",
            JobModel.status.in_([DBJobStatus.PENDING, DBJobStatus.PROCESSING])
        ).all()

        return [self._model_to_crawler_job(db_job) for db_job in db_jobs]

    async def find_crawler_executions(self, crawler_job_id: str) -> List[Job]:
        """
        Busca histórico de execuções de um crawler.

        Execuções são jobs com parent_job_id apontando para o crawler.

        Args:
            crawler_job_id: Crawler job ID

        Returns:
            Lista de Job entities (execuções)
        """
        db_jobs = self.session.query(JobModel).filter(
            JobModel.parent_job_id == crawler_job_id
        ).order_by(JobModel.created_at.desc()).all()

        return [self._model_to_entity(db_job) for db_job in db_jobs]

    # ============================================
    # Conversões Entity <-> Model
    # ============================================

    def _entity_to_model(self, job: Job) -> JobModel:
        """Converte Job entity para ORM model"""
        model = JobModel(
            id=job.id,
            user_id=job.user_id,
            filename=job.filename,
            source_type=job.source_type,
            source_url=job.source_url,
            file_size_bytes=job.file_size_bytes,
            mime_type=job.mime_type,
            status=self._status_to_db_status(job.status),
            progress=job.progress,
            error_message=job.error_message,
            total_pages=job.total_pages,
            pages_completed=job.pages_completed,
            pages_failed=job.pages_failed,
            parent_job_id=job.parent_job_id,
            job_type=job.job_type.value,
            char_count=job.char_count,
            has_elasticsearch_result=job.has_result_stored,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            updated_at=job.updated_at,
        )

        # Handle CrawlerJob-specific fields (STI pattern)
        if isinstance(job, CrawlerJob):
            if job.crawler_config:
                model.crawler_config = job.crawler_config.to_dict()
            if job.crawler_schedule:
                model.crawler_schedule = job.crawler_schedule.to_dict()

        return model

    def _update_model_from_entity(self, db_job: JobModel, job: Job) -> None:
        """Atualiza model existente com dados da entity"""
        db_job.status = self._status_to_db_status(job.status)
        db_job.progress = job.progress
        db_job.error_message = job.error_message
        db_job.total_pages = job.total_pages
        db_job.pages_completed = job.pages_completed
        db_job.pages_failed = job.pages_failed
        db_job.char_count = job.char_count
        db_job.has_elasticsearch_result = job.has_result_stored
        db_job.started_at = job.started_at
        db_job.completed_at = job.completed_at
        db_job.updated_at = job.updated_at

        # Handle CrawlerJob-specific fields (STI pattern)
        if isinstance(job, CrawlerJob):
            if job.crawler_config:
                db_job.crawler_config = job.crawler_config.to_dict()
            if job.crawler_schedule:
                db_job.crawler_schedule = job.crawler_schedule.to_dict()

    def _model_to_entity(self, db_job: JobModel) -> Job:
        """
        Converte ORM model para Job entity

        Checks job_type and returns CrawlerJob if applicable (STI pattern)
        """
        # Check if this is a crawler job (STI discriminator)
        if db_job.job_type == "crawler":
            return self._model_to_crawler_job(db_job)

        # Regular job
        return Job(
            id=db_job.id,
            user_id=db_job.user_id,
            job_type=JobType(db_job.job_type),
            status=self._db_status_to_status(db_job.status),
            filename=db_job.filename,
            source_type=db_job.source_type,
            source_url=db_job.source_url,
            file_size_bytes=db_job.file_size_bytes,
            mime_type=db_job.mime_type,
            progress=db_job.progress or 0,
            error_message=db_job.error_message,
            total_pages=db_job.total_pages,
            pages_completed=db_job.pages_completed or 0,
            pages_failed=db_job.pages_failed or 0,
            parent_job_id=db_job.parent_job_id,
            page_number=None,  # Not stored in Job table
            child_job_ids=[],  # Would need separate query
            char_count=db_job.char_count,
            has_result_stored=db_job.has_elasticsearch_result or False,
            created_at=db_job.created_at,
            started_at=db_job.started_at,
            completed_at=db_job.completed_at,
            updated_at=db_job.updated_at,
            name=None,  # Not stored in current schema
        )

    def _status_to_db_status(self, status: JobStatus) -> DBJobStatus:
        """Converte JobStatus entity para DBJobStatus"""
        mapping = {
            JobStatus.PENDING: DBJobStatus.PENDING,
            JobStatus.QUEUED: DBJobStatus.PENDING,  # Map to PENDING
            JobStatus.PROCESSING: DBJobStatus.PROCESSING,
            JobStatus.COMPLETED: DBJobStatus.COMPLETED,
            JobStatus.FAILED: DBJobStatus.FAILED,
            JobStatus.CANCELLED: DBJobStatus.CANCELLED,
        }
        return mapping.get(status, DBJobStatus.PENDING)

    def _db_status_to_status(self, db_status: DBJobStatus) -> JobStatus:
        """Converte DBJobStatus para JobStatus entity"""
        mapping = {
            DBJobStatus.PENDING: JobStatus.PENDING,
            DBJobStatus.PROCESSING: JobStatus.PROCESSING,
            DBJobStatus.COMPLETED: JobStatus.COMPLETED,
            DBJobStatus.FAILED: JobStatus.FAILED,
            DBJobStatus.CANCELLED: JobStatus.CANCELLED,
        }
        return mapping.get(db_status, JobStatus.PENDING)

    def _model_to_crawler_job(self, db_job: JobModel) -> CrawlerJob:
        """
        Converte ORM model para CrawlerJob entity.

        Deserializa JSON fields (crawler_config, crawler_schedule) para value objects.

        Args:
            db_job: JobModel ORM instance

        Returns:
            CrawlerJob entity

        Raises:
            ValueError: Se JSON inválido ou campos obrigatórios faltando
        """
        # Deserialize crawler_config
        crawler_config = None
        if db_job.crawler_config:
            try:
                crawler_config = CrawlerConfig.from_dict(db_job.crawler_config)
            except Exception as e:
                logger.error(f"Failed to deserialize crawler_config for job {db_job.id}: {e}")
                raise ValueError(f"Invalid crawler_config: {e}")

        # Deserialize crawler_schedule
        crawler_schedule = None
        if db_job.crawler_schedule:
            try:
                crawler_schedule = CrawlerSchedule.from_dict(db_job.crawler_schedule)
            except Exception as e:
                logger.error(f"Failed to deserialize crawler_schedule for job {db_job.id}: {e}")
                raise ValueError(f"Invalid crawler_schedule: {e}")

        return CrawlerJob(
            id=db_job.id,
            user_id=db_job.user_id,
            job_type=JobType.CRAWLER,
            status=self._db_status_to_status(db_job.status),
            filename=db_job.filename,
            source_type=db_job.source_type,
            source_url=db_job.source_url,
            file_size_bytes=db_job.file_size_bytes,
            mime_type=db_job.mime_type,
            progress=db_job.progress or 0,
            error_message=db_job.error_message,
            total_pages=db_job.total_pages,
            pages_completed=db_job.pages_completed or 0,
            pages_failed=db_job.pages_failed or 0,
            parent_job_id=db_job.parent_job_id,
            page_number=None,
            child_job_ids=[],
            char_count=db_job.char_count,
            has_result_stored=db_job.has_elasticsearch_result or False,
            created_at=db_job.created_at,
            started_at=db_job.started_at,
            completed_at=db_job.completed_at,
            updated_at=db_job.updated_at,
            name=db_job.name,
            crawler_config=crawler_config,
            crawler_schedule=crawler_schedule,
        )
