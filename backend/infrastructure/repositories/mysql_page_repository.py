"""
MySQL Page Repository - Concrete implementation using SQLAlchemy
"""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from domain.entities.page import Page, PageStatus
from domain.repositories.page_repository import PageRepository
from shared.models import Page as PageModel, JobStatus as DBJobStatus
from shared.database import SessionLocal

logger = logging.getLogger(__name__)


class MySQLPageRepository(PageRepository):
    """
    Implementação concreta de PageRepository usando MySQL
    """

    def __init__(self, session: Optional[Session] = None):
        self.session = session or SessionLocal()

    async def save(self, page: Page) -> None:
        """Salva ou atualiza página"""
        db_page = self.session.query(PageModel).filter(PageModel.id == page.id).first()

        if db_page:
            self._update_model_from_entity(db_page, page)
        else:
            db_page = self._entity_to_model(page)
            self.session.add(db_page)

        try:
            self.session.commit()
            logger.debug(f"Page {page.id} saved to MySQL")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to save page {page.id}: {e}", exc_info=True)
            raise

    async def find_by_id(self, page_id: str) -> Optional[Page]:
        """Busca página por ID"""
        db_page = self.session.query(PageModel).filter(PageModel.id == page_id).first()

        if not db_page:
            return None

        return self._model_to_entity(db_page)

    async def find_by_job_id(self, job_id: str) -> List[Page]:
        """Busca todas páginas de um job"""
        db_pages = self.session.query(PageModel).filter(
            PageModel.job_id == job_id
        ).order_by(PageModel.page_number).all()

        return [self._model_to_entity(db_page) for db_page in db_pages]

    async def find_by_job_and_number(self, job_id: str, page_number: int) -> Optional[Page]:
        """Busca página específica"""
        db_page = self.session.query(PageModel).filter(
            PageModel.job_id == job_id,
            PageModel.page_number == page_number
        ).first()

        if not db_page:
            return None

        return self._model_to_entity(db_page)

    async def count_by_status(self, job_id: str, status: PageStatus) -> int:
        """Conta páginas com determinado status"""
        return self.session.query(PageModel).filter(
            PageModel.job_id == job_id,
            PageModel.status == self._status_to_db_status(status)
        ).count()

    async def update_status(self, page_id: str, status: PageStatus) -> bool:
        """Atualiza status de página"""
        try:
            updated = self.session.query(PageModel).filter(
                PageModel.id == page_id
            ).update({"status": self._status_to_db_status(status)})

            self.session.commit()
            return updated > 0
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to update status for page {page_id}: {e}")
            return False

    async def delete_by_job_id(self, job_id: str) -> int:
        """Deleta todas páginas de um job"""
        try:
            deleted = self.session.query(PageModel).filter(
                PageModel.job_id == job_id
            ).delete()

            self.session.commit()
            return deleted
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to delete pages for job {job_id}: {e}")
            return 0

    # ============================================
    # Conversões Entity <-> Model
    # ============================================

    def _entity_to_model(self, page: Page) -> PageModel:
        """Converte Page entity para ORM model"""
        return PageModel(
            id=page.id,
            job_id=page.job_id,
            page_number=page.page_number,
            page_job_id=page.page_job_id,
            status=self._status_to_db_status(page.status),
            error_message=page.error_message,
            char_count=page.char_count,
            has_elasticsearch_result=page.has_result_stored,
            created_at=page.created_at,
            completed_at=page.completed_at,
            updated_at=page.updated_at,
        )

    def _update_model_from_entity(self, db_page: PageModel, page: Page) -> None:
        """Atualiza model existente"""
        db_page.page_job_id = page.page_job_id
        db_page.status = self._status_to_db_status(page.status)
        db_page.error_message = page.error_message
        db_page.char_count = page.char_count
        db_page.has_elasticsearch_result = page.has_result_stored
        db_page.completed_at = page.completed_at
        db_page.updated_at = page.updated_at

    def _model_to_entity(self, db_page: PageModel) -> Page:
        """Converte ORM model para Page entity"""
        return Page(
            id=db_page.id,
            job_id=db_page.job_id,
            page_number=db_page.page_number,
            status=self._db_status_to_status(db_page.status),
            page_job_id=db_page.page_job_id,
            char_count=db_page.char_count,
            has_result_stored=db_page.has_elasticsearch_result or False,
            error_message=db_page.error_message,
            created_at=db_page.created_at,
            completed_at=db_page.completed_at,
            updated_at=db_page.updated_at,
        )

    def _status_to_db_status(self, status: PageStatus) -> DBJobStatus:
        """Converte PageStatus para DBJobStatus"""
        mapping = {
            PageStatus.PENDING: DBJobStatus.PENDING,
            PageStatus.PROCESSING: DBJobStatus.PROCESSING,
            PageStatus.COMPLETED: DBJobStatus.COMPLETED,
            PageStatus.FAILED: DBJobStatus.FAILED,
        }
        return mapping.get(status, DBJobStatus.PENDING)

    def _db_status_to_status(self, db_status: DBJobStatus) -> PageStatus:
        """Converte DBJobStatus para PageStatus"""
        mapping = {
            DBJobStatus.PENDING: PageStatus.PENDING,
            DBJobStatus.PROCESSING: PageStatus.PROCESSING,
            DBJobStatus.COMPLETED: PageStatus.COMPLETED,
            DBJobStatus.FAILED: PageStatus.FAILED,
            DBJobStatus.CANCELLED: PageStatus.FAILED,
        }
        return mapping.get(db_status, PageStatus.PENDING)
