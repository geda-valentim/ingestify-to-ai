"""
User Entity - Represents an authenticated user
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """
    Entidade User - representa um usuário autenticado

    Regras de negócio:
    - Email deve ser único
    - Username deve ser único
    - Usuários inativos não podem fazer login
    """
    id: str
    email: str
    username: str
    hashed_password: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validações pós-inicialização"""
        self._validate_email()
        self._validate_username()

    def _validate_email(self):
        """Validação básica de email"""
        if not self.email or "@" not in self.email:
            raise ValueError(f"Invalid email: {self.email}")

    def _validate_username(self):
        """Validação básica de username"""
        if not self.username or len(self.username) < 3:
            raise ValueError(f"Username must be at least 3 characters")

    def deactivate(self) -> None:
        """Desativa usuário"""
        self.is_active = False
        self.updated_at = datetime.utcnow()

    def activate(self) -> None:
        """Ativa usuário"""
        self.is_active = True
        self.updated_at = datetime.utcnow()

    def can_login(self) -> bool:
        """Verifica se usuário pode fazer login"""
        return self.is_active
