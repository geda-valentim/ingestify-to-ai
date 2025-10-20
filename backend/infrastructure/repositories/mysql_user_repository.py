"""
MySQL User Repository - Concrete implementation using SQLAlchemy
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session

from domain.entities.user import User
from domain.repositories.user_repository import UserRepository
from shared.models import User as UserModel
from shared.database import SessionLocal

logger = logging.getLogger(__name__)


class MySQLUserRepository(UserRepository):
    """
    Implementação concreta de UserRepository usando MySQL
    """

    def __init__(self, session: Optional[Session] = None):
        self.session = session or SessionLocal()

    async def save(self, user: User) -> None:
        """Salva ou atualiza usuário"""
        db_user = self.session.query(UserModel).filter(UserModel.id == user.id).first()

        if db_user:
            self._update_model_from_entity(db_user, user)
        else:
            db_user = self._entity_to_model(user)
            self.session.add(db_user)

        try:
            self.session.commit()
            logger.debug(f"User {user.id} saved to MySQL")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to save user {user.id}: {e}", exc_info=True)
            raise

    async def find_by_id(self, user_id: str) -> Optional[User]:
        """Busca usuário por ID"""
        db_user = self.session.query(UserModel).filter(UserModel.id == user_id).first()

        if not db_user:
            return None

        return self._model_to_entity(db_user)

    async def find_by_email(self, email: str) -> Optional[User]:
        """Busca usuário por email"""
        db_user = self.session.query(UserModel).filter(UserModel.email == email).first()

        if not db_user:
            return None

        return self._model_to_entity(db_user)

    async def find_by_username(self, username: str) -> Optional[User]:
        """Busca usuário por username"""
        db_user = self.session.query(UserModel).filter(
            UserModel.username == username
        ).first()

        if not db_user:
            return None

        return self._model_to_entity(db_user)

    async def exists_by_email(self, email: str) -> bool:
        """Verifica se email existe"""
        return self.session.query(UserModel).filter(
            UserModel.email == email
        ).count() > 0

    async def exists_by_username(self, username: str) -> bool:
        """Verifica se username existe"""
        return self.session.query(UserModel).filter(
            UserModel.username == username
        ).count() > 0

    async def delete(self, user_id: str) -> bool:
        """Deleta usuário"""
        try:
            deleted = self.session.query(UserModel).filter(
                UserModel.id == user_id
            ).delete()

            self.session.commit()
            return deleted > 0
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to delete user {user_id}: {e}")
            return False

    # ============================================
    # Conversões Entity <-> Model
    # ============================================

    def _entity_to_model(self, user: User) -> UserModel:
        """Converte User entity para ORM model"""
        return UserModel(
            id=user.id,
            email=user.email,
            username=user.username,
            hashed_password=user.hashed_password,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    def _update_model_from_entity(self, db_user: UserModel, user: User) -> None:
        """Atualiza model existente"""
        db_user.email = user.email
        db_user.username = user.username
        db_user.hashed_password = user.hashed_password
        db_user.is_active = user.is_active
        db_user.updated_at = user.updated_at

    def _model_to_entity(self, db_user: UserModel) -> User:
        """Converte ORM model para User entity"""
        return User(
            id=db_user.id,
            email=db_user.email,
            username=db_user.username,
            hashed_password=db_user.hashed_password,
            is_active=db_user.is_active,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at,
        )
