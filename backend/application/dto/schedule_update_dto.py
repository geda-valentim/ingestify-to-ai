"""
Schedule Update DTO - Data Transfer Object for schedule operations

DTOs para atualização e gerenciamento de agendamentos de crawler.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


class ScheduleUpdateDTO(BaseModel):
    """
    DTO para atualizar agendamento de crawler job.

    Permite alternar entre one_time e recurring, ou desabilitar schedule.
    """
    schedule_type: Optional[str] = Field(
        default=None,
        pattern="^(one_time|recurring|disabled)$",
        description="Tipo: one_time, recurring, ou disabled (remove schedule)"
    )
    cron_expression: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Nova expressão cron (para recurring)"
    )
    timezone: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Novo timezone"
    )

    @field_validator('cron_expression')
    @classmethod
    def validate_cron_for_recurring(cls, v, info):
        """Se schedule_type=recurring, cron_expression é obrigatório"""
        if info.data.get('schedule_type') == 'recurring' and not v:
            raise ValueError("cron_expression is required for recurring schedules")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "schedule_type": "recurring",
                "cron_expression": "0 3 * * *",
                "timezone": "UTC"
            }
        }


class ScheduleUpdateResponseDTO(BaseModel):
    """Resposta da atualização de schedule"""
    job_id: str = Field(..., description="ID do job")
    message: str = Field(..., description="Mensagem de sucesso")
    schedule_type: Optional[str] = Field(
        default=None,
        description="Novo tipo de schedule (ou None se desabilitado)"
    )
    next_execution: Optional[datetime] = Field(
        default=None,
        description="Próxima execução agendada"
    )
    next_runs: List[datetime] = Field(
        default_factory=list,
        description="Próximas 5 execuções (para recurring)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Avisos sobre a atualização"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-123",
                "message": "Schedule updated successfully",
                "schedule_type": "recurring",
                "next_execution": "2025-01-14T03:00:00Z",
                "next_runs": [
                    "2025-01-14T03:00:00Z",
                    "2025-01-15T03:00:00Z",
                    "2025-01-16T03:00:00Z"
                ],
                "warnings": []
            }
        }


class ScheduleInfoDTO(BaseModel):
    """
    Informações detalhadas sobre schedule de um job.

    Usado para GET /api/crawler/jobs/{job_id}/schedule
    """
    job_id: str = Field(..., description="ID do job")
    schedule_type: Optional[str] = Field(
        default=None,
        description="Tipo: one_time, recurring, ou None (sem schedule)"
    )
    cron_expression: Optional[str] = Field(
        default=None,
        description="Expressão cron"
    )
    timezone: str = Field(default="UTC", description="Timezone")

    # Próximas execuções
    next_execution: Optional[datetime] = Field(
        default=None,
        description="Próxima execução"
    )
    next_runs: List[datetime] = Field(
        default_factory=list,
        description="Próximas 5 execuções"
    )

    # Última execução
    last_execution: Optional[datetime] = Field(
        default=None,
        description="Última execução"
    )

    # Status
    is_active: bool = Field(..., description="True se schedule está ativo")
    is_paused: bool = Field(..., description="True se job está pausado")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-123",
                "schedule_type": "recurring",
                "cron_expression": "0 2 * * *",
                "timezone": "UTC",
                "next_execution": "2025-01-14T02:00:00Z",
                "next_runs": [
                    "2025-01-14T02:00:00Z",
                    "2025-01-15T02:00:00Z",
                    "2025-01-16T02:00:00Z"
                ],
                "last_execution": "2025-01-13T02:00:00Z",
                "is_active": True,
                "is_paused": False
            }
        }


class DisableScheduleDTO(BaseModel):
    """Requisição para desabilitar schedule"""
    cancel_pending_executions: bool = Field(
        default=True,
        description="Cancelar execuções pendentes agendadas"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "cancel_pending_executions": True
            }
        }


class EnableScheduleDTO(BaseModel):
    """Requisição para reabilitar schedule"""
    start_immediately: bool = Field(
        default=False,
        description="Executar imediatamente ao reabilitar"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "start_immediately": False
            }
        }
