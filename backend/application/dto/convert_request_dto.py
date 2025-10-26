"""Convert Request DTO"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class ConvertRequestDTO:
    """
    DTO para requisição de conversão

    Representa dados de entrada para conversão de documento
    """
    user_id: str
    source_type: str  # file, url, gdrive, dropbox
    source: str  # File path, URL, or ID

    # Optional
    filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    name: Optional[str] = None  # Display name
    options: Dict[str, Any] = None
    auth_token: Optional[str] = None
    callback_url: Optional[str] = None

    def __post_init__(self):
        """Validações"""
        if self.options is None:
            self.options = {}

        valid_sources = ["file", "url", "gdrive", "dropbox"]
        if self.source_type not in valid_sources:
            raise ValueError(f"Invalid source_type: {self.source_type}")

    @property
    def display_name(self) -> str:
        """Retorna nome para exibição"""
        if self.name:
            return self.name
        if self.filename:
            return self.filename
        if self.source_type == "url":
            return self.source.split('/')[-1] or self.source
        return f"Job from {self.source_type}"
