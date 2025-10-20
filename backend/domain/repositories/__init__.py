"""Repository Interfaces (Abstractions)"""
from .job_repository import JobRepository
from .page_repository import PageRepository
from .user_repository import UserRepository

__all__ = ["JobRepository", "PageRepository", "UserRepository"]
