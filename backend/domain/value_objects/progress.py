"""
Progress Value Object - Represents job progress percentage
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    """
    Value Object para progresso (0-100)

    Garante que progresso está sempre em range válido
    """
    value: int

    def __post_init__(self):
        """Valida que progresso está entre 0 e 100"""
        if not 0 <= self.value <= 100:
            raise ValueError(f"Progress must be between 0 and 100, got {self.value}")

    @classmethod
    def zero(cls) -> "Progress":
        """Cria progresso inicial (0%)"""
        return cls(value=0)

    @classmethod
    def complete(cls) -> "Progress":
        """Cria progresso completo (100%)"""
        return cls(value=100)

    @classmethod
    def from_pages(cls, completed: int, total: int) -> "Progress":
        """
        Calcula progresso baseado em páginas completadas

        Args:
            completed: Número de páginas completadas
            total: Total de páginas

        Returns:
            Progress object
        """
        if total == 0:
            return cls.zero()

        percentage = int((completed / total) * 100)
        return cls(value=percentage)

    def is_complete(self) -> bool:
        """Verifica se progresso está completo"""
        return self.value == 100

    def is_started(self) -> bool:
        """Verifica se progresso iniciou"""
        return self.value > 0

    def __str__(self) -> str:
        return f"{self.value}%"

    def __int__(self) -> int:
        return self.value
