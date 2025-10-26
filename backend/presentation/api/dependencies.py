"""
FastAPI Dependencies for Dependency Injection

Fornece Use Cases e dependências via FastAPI Depends()
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from infrastructure.di_container import DIContainer
from shared.database import SessionLocal
from shared.auth import get_current_active_user
from shared.models import User

from application.use_cases.convert_document import ConvertDocumentUseCase
from application.use_cases.get_job_status import GetJobStatusUseCase
from application.use_cases.get_job_result import GetJobResultUseCase


# ============================================
# Database Session
# ============================================

def get_db() -> Session:
    """
    Dependency: Database session

    Yields:
        SQLAlchemy Session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================
# DI Container
# ============================================

def get_container(db: Session = Depends(get_db)) -> DIContainer:
    """
    Dependency: DI Container

    Args:
        db: Database session

    Returns:
        DIContainer
    """
    return DIContainer(db_session=db)


# ============================================
# Use Cases
# ============================================

def get_convert_document_use_case(
    container: DIContainer = Depends(get_container)
) -> ConvertDocumentUseCase:
    """
    Dependency: Convert Document Use Case

    Args:
        container: DI Container

    Returns:
        ConvertDocumentUseCase
    """
    return container.get_convert_document_use_case()


def get_get_job_status_use_case(
    container: DIContainer = Depends(get_container)
) -> GetJobStatusUseCase:
    """
    Dependency: Get Job Status Use Case

    Args:
        container: DI Container

    Returns:
        GetJobStatusUseCase
    """
    return container.get_get_job_status_use_case()


def get_get_job_result_use_case(
    container: DIContainer = Depends(get_container)
) -> GetJobResultUseCase:
    """
    Dependency: Get Job Result Use Case

    Args:
        container: DI Container

    Returns:
        GetJobResultUseCase
    """
    return container.get_get_job_result_use_case()


# ============================================
# Authentication
# ============================================

def get_current_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Dependency: Current authenticated user

    Args:
        current_user: User from auth middleware

    Returns:
        User
    """
    return current_user
