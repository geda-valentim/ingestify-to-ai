"""
Create Crawler Job DTO - Data for creating new crawler jobs

DTO para requisição de criação de crawler job.
Valida inputs e define valores padrão.
"""
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional


class CreateCrawlerConfigDTO(BaseModel):
    """Configuração do crawler para criação"""
    mode: str = Field(
        default="page_only",
        description="Modo: page_only, with_pdfs, with_images, full_assets",
        pattern="^(page_only|with_pdfs|with_images|full_assets)$"
    )
    engine: str = Field(
        default="beautifulsoup",
        description="Engine: beautifulsoup ou playwright",
        pattern="^(beautifulsoup|playwright)$"
    )
    max_depth: int = Field(default=1, ge=0, le=10)
    max_pages: int = Field(default=100, ge=1, le=10000)
    respect_robots_txt: bool = Field(default=True)
    follow_external_links: bool = Field(default=False)

    # Retry
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: int = Field(default=5, ge=0, le=300)

    # Assets
    download_images: bool = Field(default=False)
    download_css: bool = Field(default=False)
    download_js: bool = Field(default=False)

    # Proxy (opcional)
    use_proxy: bool = Field(default=False)
    proxy_host: Optional[str] = Field(default=None, max_length=255)
    proxy_port: Optional[int] = Field(default=None, ge=1, le=65535)
    proxy_username: Optional[str] = Field(default=None, max_length=255)
    proxy_password: Optional[str] = Field(default=None, max_length=255)

    @field_validator('proxy_host', 'proxy_port', 'proxy_username', 'proxy_password')
    @classmethod
    def validate_proxy_fields(cls, v, info):
        """Valida que proxy_* só pode ser preenchido se use_proxy=True"""
        # Note: validação completa será feita no Use Case
        return v


class CreateCrawlerScheduleDTO(BaseModel):
    """Agendamento para criação"""
    schedule_type: str = Field(
        ...,
        description="Tipo: one_time ou recurring",
        pattern="^(one_time|recurring)$"
    )
    cron_expression: Optional[str] = Field(
        default=None,
        description="Expressão cron (obrigatório para recurring)",
        max_length=255
    )
    timezone: str = Field(
        default="UTC",
        description="Timezone (ex: UTC, America/Sao_Paulo)",
        max_length=50
    )

    @field_validator('cron_expression')
    @classmethod
    def validate_cron_for_recurring(cls, v, info):
        """Se schedule_type=recurring, cron_expression é obrigatório"""
        if info.data.get('schedule_type') == 'recurring' and not v:
            raise ValueError("cron_expression is required for recurring schedules")
        return v


class CreateCrawlerJobDTO(BaseModel):
    """
    DTO para criar novo crawler job.

    Validações:
    - URL válida
    - Nome não vazio
    - Configurações válidas
    - Cron expression válida (se recurring)
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Nome do job (ex: 'Crawl Documentation')"
    )
    source_url: HttpUrl = Field(
        ...,
        description="URL a ser crawleada (deve ser http/https)"
    )
    config: CreateCrawlerConfigDTO = Field(
        default_factory=CreateCrawlerConfigDTO,
        description="Configuração do crawler (usa defaults se não informado)"
    )
    schedule: Optional[CreateCrawlerScheduleDTO] = Field(
        default=None,
        description="Agendamento (opcional, null = execução manual)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Crawl Documentation Site",
                "source_url": "https://example.com/docs",
                "config": {
                    "mode": "page_only",
                    "engine": "beautifulsoup",
                    "max_depth": 2,
                    "max_pages": 100,
                    "respect_robots_txt": True,
                    "follow_external_links": False
                },
                "schedule": {
                    "schedule_type": "recurring",
                    "cron_expression": "0 2 * * *",
                    "timezone": "UTC"
                }
            }
        }


class CreateCrawlerJobResponseDTO(BaseModel):
    """Resposta da criação de crawler job"""
    job_id: str = Field(..., description="ID do job criado")
    name: str = Field(..., description="Nome do job")
    source_url: str = Field(..., description="URL a ser crawleada")
    status: str = Field(..., description="Status inicial (active/paused)")
    message: str = Field(..., description="Mensagem de sucesso")
    warnings: list[str] = Field(
        default_factory=list,
        description="Avisos (ex: jobs similares encontrados)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-123",
                "name": "Crawl Documentation Site",
                "source_url": "https://example.com/docs",
                "status": "active",
                "message": "Crawler job created successfully",
                "warnings": [
                    "Similar crawler job found: 'Old Documentation Crawler' (job-456)"
                ]
            }
        }
