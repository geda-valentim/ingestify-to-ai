"""
Duplicate Warning DTO - Data Transfer Object for duplicate detection

DTOs para avisar sobre jobs/URLs duplicados ou similares.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class DuplicateJobDTO(BaseModel):
    """Informação sobre job duplicado/similar"""
    job_id: str = Field(..., description="ID do job similar")
    name: str = Field(..., description="Nome do job")
    source_url: str = Field(..., description="URL do job")
    normalized_url: str = Field(..., description="URL normalizada")
    url_pattern: str = Field(..., description="Padrão da URL")
    status: str = Field(..., description="Status do job")
    similarity_type: str = Field(
        ...,
        description="Tipo de similaridade: exact_url, same_pattern, same_domain"
    )
    created_at: str = Field(..., description="Data de criação")


class DuplicateWarningDTO(BaseModel):
    """
    Aviso sobre jobs duplicados ou similares.

    Retornado durante criação de novo crawler job quando
    detectados jobs similares existentes.
    """
    has_duplicates: bool = Field(..., description="True se encontrou duplicatas")
    total_similar: int = Field(..., description="Total de jobs similares")

    similar_jobs: List[DuplicateJobDTO] = Field(
        default_factory=list,
        description="Lista de jobs similares encontrados"
    )

    recommendation: str = Field(
        ...,
        description="Recomendação: continue, review, or merge"
    )

    message: str = Field(
        ...,
        description="Mensagem explicativa para o usuário"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "has_duplicates": True,
                "total_similar": 2,
                "similar_jobs": [
                    {
                        "job_id": "job-456",
                        "name": "Old Documentation Crawler",
                        "source_url": "https://example.com/docs",
                        "normalized_url": "https://example.com/docs",
                        "url_pattern": "https://example.com/docs",
                        "status": "active",
                        "similarity_type": "exact_url",
                        "created_at": "2025-01-01T00:00:00Z"
                    },
                    {
                        "job_id": "job-789",
                        "name": "API Documentation",
                        "source_url": "https://example.com/api",
                        "normalized_url": "https://example.com/api",
                        "url_pattern": "https://example.com/api",
                        "status": "active",
                        "similarity_type": "same_domain",
                        "created_at": "2025-01-05T00:00:00Z"
                    }
                ],
                "recommendation": "review",
                "message": "Found 1 exact duplicate and 1 job on same domain. Consider reviewing existing crawlers before creating new one."
            }
        }


class DuplicateCheckRequestDTO(BaseModel):
    """Requisição para verificar duplicatas antes de criar job"""
    source_url: str = Field(..., description="URL para verificar")
    check_exact: bool = Field(
        default=True,
        description="Verificar URL exata (normalizada)"
    )
    check_pattern: bool = Field(
        default=True,
        description="Verificar mesmo padrão de URL"
    )
    check_domain: bool = Field(
        default=False,
        description="Verificar outros jobs no mesmo domínio"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "source_url": "https://example.com/docs",
                "check_exact": True,
                "check_pattern": True,
                "check_domain": False
            }
        }


class DuplicateCheckResponseDTO(BaseModel):
    """Resposta da verificação de duplicatas"""
    source_url: str = Field(..., description="URL verificada")
    normalized_url: str = Field(..., description="URL normalizada")
    url_pattern: str = Field(..., description="Padrão gerado")
    domain: str = Field(..., description="Domínio extraído")

    # Resultados
    exact_matches: int = Field(..., description="URLs exatas encontradas")
    pattern_matches: int = Field(..., description="Padrões similares encontrados")
    domain_matches: int = Field(..., description="Jobs no mesmo domínio")

    warning: Optional[DuplicateWarningDTO] = Field(
        default=None,
        description="Aviso de duplicatas (se encontradas)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "source_url": "https://example.com/docs",
                "normalized_url": "https://example.com/docs",
                "url_pattern": "https://example.com/docs",
                "domain": "example.com",
                "exact_matches": 1,
                "pattern_matches": 0,
                "domain_matches": 3,
                "warning": {
                    "has_duplicates": True,
                    "total_similar": 1,
                    "similar_jobs": [
                        {
                            "job_id": "job-456",
                            "name": "Old Documentation Crawler",
                            "source_url": "https://example.com/docs",
                            "normalized_url": "https://example.com/docs",
                            "url_pattern": "https://example.com/docs",
                            "status": "active",
                            "similarity_type": "exact_url",
                            "created_at": "2025-01-01T00:00:00Z"
                        }
                    ],
                    "recommendation": "review",
                    "message": "Found exact duplicate. Consider using existing crawler instead."
                }
            }
        }
