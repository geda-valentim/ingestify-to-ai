"""
Response Schemas - Pydantic models for API output
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any


class JobCreatedResponse(BaseModel):
    """Response when job is created"""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status", example="queued")
    created_at: datetime = Field(..., description="Creation timestamp")
    message: str = Field(..., description="Human-readable message")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "queued",
                "created_at": "2025-10-19T10:00:00Z",
                "message": "Job enfileirado para processamento"
            }
        }


class JobStatusResponse(BaseModel):
    """Response for job status"""
    job_id: str = Field(..., description="Job ID")
    type: str = Field(..., description="Job type", example="main")
    status: str = Field(..., description="Job status", example="processing")
    progress: int = Field(..., description="Progress percentage (0-100)", ge=0, le=100)
    created_at: datetime = Field(..., description="Creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")
    name: Optional[str] = Field(None, description="Job display name")

    # Multi-page PDF specific
    total_pages: Optional[int] = Field(None, description="Total pages (for PDFs)")
    pages_completed: int = Field(0, description="Pages completed")
    pages_failed: int = Field(0, description="Pages failed")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "type": "main",
                "status": "processing",
                "progress": 45,
                "created_at": "2025-10-19T10:00:00Z",
                "started_at": "2025-10-19T10:00:05Z",
                "completed_at": None,
                "error": None,
                "name": "My Document",
                "total_pages": 10,
                "pages_completed": 4,
                "pages_failed": 0
            }
        }


class JobResultResponse(BaseModel):
    """Response for job result"""
    job_id: str = Field(..., description="Job ID")
    type: str = Field(..., description="Job type")
    status: str = Field(..., description="Job status", example="completed")
    result: Dict[str, Any] = Field(..., description="Conversion result (markdown + metadata)")
    completed_at: datetime = Field(..., description="Completion timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "type": "main",
                "status": "completed",
                "result": {
                    "markdown": "# My Document\n\nContent here...",
                    "metadata": {
                        "pages": 10,
                        "words": 2500,
                        "format": "pdf"
                    }
                },
                "completed_at": "2025-10-19T10:05:00Z"
            }
        }
