"""
JobId Value Object - Immutable identifier for jobs
"""
from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True)
class JobId:
    """
    Value Object para Job ID

    Garante que todos os IDs sejam UUIDs válidos
    """
    value: str

    def __post_init__(self):
        """Valida que value é um UUID válido"""
        try:
            UUID(self.value)
        except ValueError:
            raise ValueError(f"Invalid UUID: {self.value}")

    @classmethod
    def generate(cls) -> "JobId":
        """Gera um novo JobId"""
        return cls(value=str(uuid4()))

    @classmethod
    def from_string(cls, value: str) -> "JobId":
        """Cria JobId a partir de string"""
        return cls(value=value)

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"JobId({self.value})"
