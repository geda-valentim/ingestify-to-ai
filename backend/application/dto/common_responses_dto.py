"""
Common Response DTOs - Standard response patterns

DTOs para respostas comuns em toda a API de crawler.
Garante consistência nas respostas.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Any


class SuccessResponseDTO(BaseModel):
    """Resposta padrão de sucesso"""
    success: bool = Field(True, description="Sempre True para sucesso")
    message: str = Field(..., description="Mensagem de sucesso")
    data: Optional[Any] = Field(default=None, description="Dados adicionais (opcional)")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": None
            }
        }


class ErrorResponseDTO(BaseModel):
    """Resposta padrão de erro"""
    success: bool = Field(False, description="Sempre False para erro")
    error: str = Field(..., description="Tipo de erro")
    message: str = Field(..., description="Mensagem de erro")
    details: Optional[dict] = Field(default=None, description="Detalhes adicionais")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "ValidationError",
                "message": "Invalid crawler configuration",
                "details": {
                    "field": "max_depth",
                    "reason": "Must be between 0 and 10"
                }
            }
        }


class DeleteResponseDTO(BaseModel):
    """Resposta de deleção"""
    job_id: str = Field(..., description="ID do job deletado")
    message: str = Field(..., description="Mensagem de confirmação")
    cascade_deleted: Optional[dict] = Field(
        default=None,
        description="Recursos deletados em cascata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-123",
                "message": "Crawler job deleted successfully",
                "cascade_deleted": {
                    "executions": 5,
                    "crawled_files": 120,
                    "elasticsearch_docs": 1
                }
            }
        }


class PauseResponseDTO(BaseModel):
    """Resposta de pause"""
    job_id: str = Field(..., description="ID do job pausado")
    message: str = Field(..., description="Mensagem de confirmação")
    previous_status: str = Field(..., description="Status anterior")
    current_status: str = Field(..., description="Status atual (paused)")
    cancelled_executions: int = Field(
        default=0,
        description="Execuções agendadas que foram canceladas"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-123",
                "message": "Crawler job paused successfully",
                "previous_status": "active",
                "current_status": "paused",
                "cancelled_executions": 2
            }
        }


class ResumeResponseDTO(BaseModel):
    """Resposta de resume"""
    job_id: str = Field(..., description="ID do job resumido")
    message: str = Field(..., description="Mensagem de confirmação")
    previous_status: str = Field(..., description="Status anterior (paused)")
    current_status: str = Field(..., description="Status atual (active)")
    next_execution: Optional[str] = Field(
        default=None,
        description="Próxima execução agendada"
    )
    immediate_execution: bool = Field(
        default=False,
        description="True se execução foi iniciada imediatamente"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-123",
                "message": "Crawler job resumed successfully",
                "previous_status": "paused",
                "current_status": "active",
                "next_execution": "2025-01-14T02:00:00Z",
                "immediate_execution": False
            }
        }


class CancelExecutionResponseDTO(BaseModel):
    """Resposta de cancelamento de execução"""
    execution_id: str = Field(..., description="ID da execução cancelada")
    crawler_job_id: str = Field(..., description="ID do crawler job")
    message: str = Field(..., description="Mensagem de confirmação")
    previous_status: str = Field(..., description="Status anterior")
    current_status: str = Field(..., description="Status atual (cancelled)")
    partial_results: bool = Field(
        ...,
        description="True se há resultados parciais disponíveis"
    )
    pages_crawled: int = Field(
        default=0,
        description="Páginas que foram crawleadas antes do cancelamento"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec-789",
                "crawler_job_id": "job-123",
                "message": "Execution cancelled successfully",
                "previous_status": "processing",
                "current_status": "cancelled",
                "partial_results": True,
                "pages_crawled": 23
            }
        }


class ExecuteNowResponseDTO(BaseModel):
    """Resposta de execução manual"""
    execution_id: str = Field(..., description="ID da nova execução criada")
    crawler_job_id: str = Field(..., description="ID do crawler job")
    message: str = Field(..., description="Mensagem de confirmação")
    status: str = Field(..., description="Status inicial (pending/processing)")
    estimated_duration_minutes: Optional[int] = Field(
        default=None,
        description="Duração estimada baseada em execuções anteriores"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec-790",
                "crawler_job_id": "job-123",
                "message": "Crawler execution started",
                "status": "pending",
                "estimated_duration_minutes": 5
            }
        }


class ValidationErrorDTO(BaseModel):
    """Detalhes de erro de validação"""
    field: str = Field(..., description="Campo que falhou na validação")
    message: str = Field(..., description="Mensagem de erro")
    value: Optional[Any] = Field(default=None, description="Valor inválido fornecido")

    class Config:
        json_schema_extra = {
            "example": {
                "field": "config.max_depth",
                "message": "Must be between 0 and 10",
                "value": 15
            }
        }


class ValidationErrorResponseDTO(BaseModel):
    """Resposta de erro de validação (múltiplos campos)"""
    success: bool = Field(False, description="Sempre False")
    error: str = Field("ValidationError", description="Tipo de erro")
    message: str = Field(..., description="Mensagem geral")
    validation_errors: List[ValidationErrorDTO] = Field(
        ...,
        description="Lista de erros de validação"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "ValidationError",
                "message": "Invalid request data",
                "validation_errors": [
                    {
                        "field": "config.max_depth",
                        "message": "Must be between 0 and 10",
                        "value": 15
                    },
                    {
                        "field": "source_url",
                        "message": "Invalid URL format",
                        "value": "not-a-url"
                    }
                ]
            }
        }
