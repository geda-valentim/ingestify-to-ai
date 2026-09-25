"""
Update Crawler Job DTO - Data for updating crawler jobs

DTO para requisição de atualização de crawler job.
Todos os campos são opcionais (partial update).
"""
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional


class UpdateCrawlerConfigDTO(BaseModel):
    """Atualização de configuração (campos opcionais)"""
    mode: Optional[str] = Field(
        default=None,
        pattern="^(page_only|with_pdfs|with_images|full_assets)$"
    )
    engine: Optional[str] = Field(
        default=None,
        pattern="^(beautifulsoup|playwright)$"
    )
    max_depth: Optional[int] = Field(default=None, ge=0, le=10)
    max_pages: Optional[int] = Field(default=None, ge=1, le=10000)
    respect_robots_txt: Optional[bool] = Field(default=None)
    follow_external_links: Optional[bool] = Field(default=None)

    # Retry
    max_retries: Optional[int] = Field(default=None, ge=0, le=10)
    retry_delay_seconds: Optional[int] = Field(default=None, ge=0, le=300)

    # Assets
    download_images: Optional[bool] = Field(default=None)
    download_css: Optional[bool] = Field(default=None)
    download_js: Optional[bool] = Field(default=None)

    # Proxy
    use_proxy: Optional[bool] = Field(default=None)
    proxy_host: Optional[str] = Field(default=None, max_length=255)
    proxy_port: Optional[int] = Field(default=None, ge=1, le=65535)
    proxy_username: Optional[str] = Field(default=None, max_length=255)
    proxy_password: Optional[str] = Field(default=None, max_length=255)


class UpdateCrawlerScheduleDTO(BaseModel):
    """Atualização de agendamento (campos opcionais)"""
    schedule_type: Optional[str] = Field(
        default=None,
        pattern="^(one_time|recurring)$"
    )
    cron_expression: Optional[str] = Field(default=None, max_length=255)
    timezone: Optional[str] = Field(default=None, max_length=50)


class UpdateCrawlerJobDTO(BaseModel):
    """
    DTO para atualizar crawler job existente.

    Todos os campos são opcionais (partial update).
    Apenas os campos informados serão atualizados.

    Regras:
    - Não pode alterar job em execução (status=processing)
    - Alterar schedule de recurring para one_time cancela próximas execuções
    - Alterar config não afeta execuções em andamento
    """
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=1000,
        description="Novo nome do job"
    )
    source_url: Optional[HttpUrl] = Field(
        default=None,
        description="Nova URL (cria novo job internamente)"
    )
    config: Optional[UpdateCrawlerConfigDTO] = Field(
        default=None,
        description="Atualização parcial de configuração"
    )
    schedule: Optional[UpdateCrawlerScheduleDTO] = Field(
        default=None,
        description="Atualização parcial de agendamento"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Documentation Crawler",
                "config": {
                    "max_depth": 3,
                    "max_pages": 200
                },
                "schedule": {
                    "cron_expression": "0 3 * * *"
                }
            }
        }


class UpdateCrawlerJobResponseDTO(BaseModel):
    """Resposta da atualização"""
    job_id: str = Field(..., description="ID do job atualizado")
    message: str = Field(..., description="Mensagem de sucesso")
    updated_fields: list[str] = Field(
        ...,
        description="Lista de campos que foram atualizados"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Avisos sobre a atualização"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-123",
                "message": "Crawler job updated successfully",
                "updated_fields": ["name", "config.max_depth", "schedule.cron_expression"],
                "warnings": [
                    "Schedule changed: next execution rescheduled to 2025-01-14T03:00:00Z"
                ]
            }
        }
