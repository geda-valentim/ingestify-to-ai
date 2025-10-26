"""
Dependency Injection Container

Centraliza a criação e injeção de dependências para Clean Architecture
"""
import logging
from functools import lru_cache
from typing import Optional

from sqlalchemy.orm import Session

# Domain
from domain.repositories.job_repository import JobRepository
from domain.repositories.page_repository import PageRepository
from domain.repositories.user_repository import UserRepository
from domain.services.pdf_analysis_service import PDFAnalysisService
from domain.services.progress_calculator_service import ProgressCalculatorService

# Application
from application.ports.converter_port import ConverterPort
from application.ports.storage_port import StoragePort
from application.ports.queue_port import QueuePort
from application.use_cases.convert_document import ConvertDocumentUseCase
from application.use_cases.get_job_status import GetJobStatusUseCase
from application.use_cases.get_job_result import GetJobResultUseCase

# Infrastructure
from infrastructure.repositories.mysql_job_repository import MySQLJobRepository
from infrastructure.repositories.mysql_page_repository import MySQLPageRepository
from infrastructure.repositories.mysql_user_repository import MySQLUserRepository
from infrastructure.adapters.docling_adapter import DoclingConverterAdapter
from infrastructure.adapters.celery_queue_adapter import CeleryQueueAdapter
from infrastructure.adapters.elasticsearch_storage_adapter import ElasticsearchStorageAdapter

# Shared
from shared.database import SessionLocal
from shared.config import get_settings

logger = logging.getLogger(__name__)


class DIContainer:
    """
    Dependency Injection Container

    Responsável por criar e fornecer instâncias de:
    - Repositories
    - Services
    - Adapters
    - Use Cases
    """

    def __init__(self, db_session: Optional[Session] = None):
        """
        Inicializa container

        Args:
            db_session: SQLAlchemy session (opcional)
        """
        self.db_session = db_session or SessionLocal()
        self.settings = get_settings()

        # Lazy initialization
        self._job_repository: Optional[JobRepository] = None
        self._page_repository: Optional[PageRepository] = None
        self._user_repository: Optional[UserRepository] = None

        self._converter: Optional[ConverterPort] = None
        self._storage: Optional[StoragePort] = None
        self._queue: Optional[QueuePort] = None

        self._pdf_analysis_service: Optional[PDFAnalysisService] = None
        self._progress_calculator: Optional[ProgressCalculatorService] = None

    # ============================================
    # Repositories
    # ============================================

    def get_job_repository(self) -> JobRepository:
        """Retorna Job Repository"""
        if self._job_repository is None:
            self._job_repository = MySQLJobRepository(session=self.db_session)
            logger.debug("JobRepository created (MySQL)")
        return self._job_repository

    def get_page_repository(self) -> PageRepository:
        """Retorna Page Repository"""
        if self._page_repository is None:
            self._page_repository = MySQLPageRepository(session=self.db_session)
            logger.debug("PageRepository created (MySQL)")
        return self._page_repository

    def get_user_repository(self) -> UserRepository:
        """Retorna User Repository"""
        if self._user_repository is None:
            self._user_repository = MySQLUserRepository(session=self.db_session)
            logger.debug("UserRepository created (MySQL)")
        return self._user_repository

    # ============================================
    # Adapters (Ports)
    # ============================================

    def get_converter(self) -> ConverterPort:
        """Retorna Converter (Docling)"""
        if self._converter is None:
            self._converter = DoclingConverterAdapter(
                enable_ocr=self.settings.docling_enable_ocr,
                enable_table_structure=self.settings.docling_enable_table_structure
            )
            logger.debug("ConverterPort created (Docling)")
        return self._converter

    def get_storage(self) -> StoragePort:
        """Retorna Storage (Elasticsearch)"""
        if self._storage is None:
            self._storage = ElasticsearchStorageAdapter()
            logger.debug("StoragePort created (Elasticsearch)")
        return self._storage

    def get_queue(self) -> QueuePort:
        """Retorna Queue (Celery)"""
        if self._queue is None:
            self._queue = CeleryQueueAdapter()
            logger.debug("QueuePort created (Celery)")
        return self._queue

    # ============================================
    # Domain Services
    # ============================================

    def get_pdf_analysis_service(self) -> PDFAnalysisService:
        """Retorna PDF Analysis Service"""
        if self._pdf_analysis_service is None:
            self._pdf_analysis_service = PDFAnalysisService()
            logger.debug("PDFAnalysisService created")
        return self._pdf_analysis_service

    def get_progress_calculator(self) -> ProgressCalculatorService:
        """Retorna Progress Calculator Service"""
        if self._progress_calculator is None:
            self._progress_calculator = ProgressCalculatorService()
            logger.debug("ProgressCalculatorService created")
        return self._progress_calculator

    # ============================================
    # Use Cases
    # ============================================

    def get_convert_document_use_case(self) -> ConvertDocumentUseCase:
        """Retorna Convert Document Use Case"""
        return ConvertDocumentUseCase(
            job_repository=self.get_job_repository(),
            queue=self.get_queue()
        )

    def get_get_job_status_use_case(self) -> GetJobStatusUseCase:
        """Retorna Get Job Status Use Case"""
        return GetJobStatusUseCase(
            job_repository=self.get_job_repository(),
            page_repository=self.get_page_repository(),
            progress_calculator=self.get_progress_calculator()
        )

    def get_get_job_result_use_case(self) -> GetJobResultUseCase:
        """Retorna Get Job Result Use Case"""
        return GetJobResultUseCase(
            job_repository=self.get_job_repository(),
            storage=self.get_storage()
        )

    # ============================================
    # Cleanup
    # ============================================

    def close(self):
        """Fecha conexões"""
        if self.db_session:
            self.db_session.close()
            logger.debug("Database session closed")


# ============================================
# Global Container (Singleton)
# ============================================

_global_container: Optional[DIContainer] = None


@lru_cache
def get_di_container() -> DIContainer:
    """
    Retorna container global (singleton)

    Returns:
        DIContainer
    """
    global _global_container
    if _global_container is None:
        _global_container = DIContainer()
        logger.info("Global DI Container initialized")
    return _global_container


def reset_di_container():
    """Reset container (útil para testes)"""
    global _global_container
    if _global_container:
        _global_container.close()
    _global_container = None
    get_di_container.cache_clear()
    logger.info("DI Container reset")
