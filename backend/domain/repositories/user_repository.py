"""
User Repository Interface - Abstract Data Access for Users
"""
from abc import ABC, abstractmethod
from typing import Optional
from domain.entities.user import User


class UserRepository(ABC):
    """
    Interface abstrata para repositório de Users
    """

    @abstractmethod
    async def save(self, user: User) -> None:
        """
        Salva ou atualiza um usuário

        Args:
            user: User entity to save
        """
        pass

    @abstractmethod
    async def find_by_id(self, user_id: str) -> Optional[User]:
        """
        Busca usuário por ID

        Args:
            user_id: User ID

        Returns:
            User entity ou None
        """
        pass

    @abstractmethod
    async def find_by_email(self, email: str) -> Optional[User]:
        """
        Busca usuário por email

        Args:
            email: User email

        Returns:
            User entity ou None
        """
        pass

    @abstractmethod
    async def find_by_username(self, username: str) -> Optional[User]:
        """
        Busca usuário por username

        Args:
            username: Username

        Returns:
            User entity ou None
        """
        pass

    @abstractmethod
    async def exists_by_email(self, email: str) -> bool:
        """
        Verifica se email já existe

        Args:
            email: Email to check

        Returns:
            True se existe
        """
        pass

    @abstractmethod
    async def exists_by_username(self, username: str) -> bool:
        """
        Verifica se username já existe

        Args:
            username: Username to check

        Returns:
            True se existe
        """
        pass

    @abstractmethod
    async def delete(self, user_id: str) -> bool:
        """
        Deleta um usuário

        Args:
            user_id: User ID

        Returns:
            True se deletado
        """
        pass
