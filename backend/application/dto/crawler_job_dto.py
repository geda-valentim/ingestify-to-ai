"""
Crawler Job DTO - Data Transfer Object for CrawlerJob

DTOs são usados para transferir dados entre camadas (Application <-> API).
Separam a representação externa da estrutura interna do domínio.
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime


class CrawlerConfigDTO(BaseModel):
    """Configuração do crawler"""
    mode: str = Field(..., description="Modo do crawler: page_only, with_pdfs, with_images, full_assets")
    engine: str = Field(..., description="Engine: beautifulsoup ou playwright")
    max_depth: int = Field(default=1, ge=0, le=10, description="Profundidade máxima de crawling")
    max_pages: int = Field(default=100, ge=1, le=10000, description="Máximo de páginas a crawlear")
    respect_robots_txt: bool = Field(default=True, description="Respeitar robots.txt")
    follow_external_links: bool = Field(default=False, description="Seguir links externos")

    # Retry config
    max_retries: int = Field(default=3, ge=0, le=10, description="Máximo de tentativas")
    retry_delay_seconds: int = Field(default=5, ge=0, le=300, description="Delay entre retries")

    # Asset download
    download_images: bool = Field(default=False, description="Baixar imagens")
    download_css: bool = Field(default=False, description="Baixar CSS")
    download_js: bool = Field(default=False, description="Baixar JavaScript")

    # Proxy (opcional)
    use_proxy: bool = Field(default=False, description="Usar proxy")
    proxy_host: Optional[str] = Field(default=None, description="Host do proxy")
    proxy_port: Optional[int] = Field(default=None, ge=1, le=65535, description="Porta do proxy")
    proxy_username: Optional[str] = Field(default=None, description="Usuário do proxy")
    proxy_password: Optional[str] = Field(default=None, description="Senha do proxy")


class CrawlerScheduleDTO(BaseModel):
    """Agendamento do crawler"""
    schedule_type: str = Field(..., description="Tipo: one_time ou recurring")
    cron_expression: Optional[str] = Field(default=None, description="Expressão cron (para recurring)")
    timezone: str = Field(default="UTC", description="Timezone para agendamento")
    next_runs: List[datetime] = Field(default_factory=list, description="Próximas 5 execuções")


class CrawlerJobDTO(BaseModel):
    """
    DTO completo de CrawlerJob para resposta de API.

    Representa um crawler job com todas as suas configurações e status.
    """
    id: str = Field(..., description="ID do job")
    user_id: str = Field(..., description="ID do usuário dono")
    name: str = Field(..., description="Nome do job")
    source_url: HttpUrl = Field(..., description="URL a ser crawleada")
    status: str = Field(..., description="Status: active, paused, stopped, completed, failed")

    # Configurações
    config: CrawlerConfigDTO = Field(..., description="Configuração do crawler")
    schedule: Optional[CrawlerScheduleDTO] = Field(default=None, description="Agendamento (opcional)")

    # Estatísticas
    total_executions: int = Field(default=0, description="Total de execuções realizadas")
    successful_executions: int = Field(default=0, description="Execuções bem-sucedidas")
    failed_executions: int = Field(default=0, description="Execuções falhadas")
    last_execution: Optional[datetime] = Field(default=None, description="Última execução")
    next_execution: Optional[datetime] = Field(default=None, description="Próxima execução agendada")

    # Timestamps
    created_at: datetime = Field(..., description="Data de criação")
    updated_at: datetime = Field(..., description="Data de atualização")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "job-123",
                "user_id": "user-456",
                "name": "Crawl documentation site",
                "source_url": "https://example.com/docs",
                "status": "active",
                "config": {
                    "mode": "page_only",
                    "engine": "beautifulsoup",
                    "max_depth": 2,
                    "max_pages": 100,
                    "respect_robots_txt": True,
                    "follow_external_links": False,
                    "max_retries": 3,
                    "retry_delay_seconds": 5,
                    "download_images": False,
                    "download_css": False,
                    "download_js": False,
                    "use_proxy": False
                },
                "schedule": {
                    "schedule_type": "recurring",
                    "cron_expression": "0 2 * * *",
                    "timezone": "UTC",
                    "next_runs": ["2025-01-14T02:00:00Z"]
                },
                "total_executions": 5,
                "successful_executions": 4,
                "failed_executions": 1,
                "last_execution": "2025-01-13T02:00:00Z",
                "next_execution": "2025-01-14T02:00:00Z",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-13T02:05:00Z"
            }
        }


class CrawlerJobListDTO(BaseModel):
    """DTO para listagem de jobs (versão resumida)"""
    id: str
    user_id: str
    name: str
    source_url: HttpUrl
    status: str
    mode: str = Field(..., description="Modo do crawler")
    engine: str = Field(..., description="Engine usado")
    schedule_type: Optional[str] = Field(default=None, description="Tipo de agendamento")
    total_executions: int = Field(default=0)
    last_execution: Optional[datetime] = Field(default=None)
    next_execution: Optional[datetime] = Field(default=None)
    created_at: datetime
    updated_at: datetime


class CrawlerJobStatsDTO(BaseModel):
    """Estatísticas gerais de crawler jobs"""
    total_jobs: int = Field(..., description="Total de jobs")
    active_jobs: int = Field(..., description="Jobs ativos")
    paused_jobs: int = Field(..., description="Jobs pausados")
    stopped_jobs: int = Field(..., description="Jobs parados")
    total_executions: int = Field(..., description="Total de execuções")
    total_pages_crawled: int = Field(..., description="Total de páginas crawleadas")
    total_files_downloaded: int = Field(..., description="Total de arquivos baixados")
