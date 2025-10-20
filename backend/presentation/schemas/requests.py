"""
Request Schemas - Pydantic models for API input validation
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class ConvertRequest(BaseModel):
    """Request schema for document conversion"""
    source_type: str = Field(
        ...,
        description="Source type: file, url, gdrive, dropbox",
        example="file"
    )
    source: Optional[str] = Field(
        None,
        description="Source identifier (URL, file ID, etc.)",
        example="https://example.com/document.pdf"
    )
    name: Optional[str] = Field(
        None,
        description="Optional job name",
        example="Monthly Report"
    )
    options: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Conversion options",
        example={"enable_ocr": False}
    )

    class Config:
        json_schema_extra = {
            "example": {
                "source_type": "url",
                "source": "https://example.com/document.pdf",
                "name": "Example Document",
                "options": {
                    "enable_ocr": False,
                    "enable_tables": True
                }
            }
        }
