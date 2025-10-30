import os
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class DoclingConverter:
    """Wrapper for Docling document converter"""

    def __init__(self, enable_ocr: bool = False, enable_table_structure: bool = True, enable_images: bool = False):
        """
        Initialize Docling converter with optimizations

        Args:
            enable_ocr: Enable OCR for scanned documents (slower, disable for digital PDFs)
            enable_table_structure: Enable table structure recognition (disable if no tables needed)
            enable_images: Enable image extraction and processing (slower, disable for text-only conversion)
        """
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption, InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions

            # Try to import optimized backend (if available)
            backend = None
            backend_name = "default"
            try:
                from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
                backend = DoclingParseDocumentBackend
                backend_name = "DoclingParse"
            except ImportError:
                try:
                    # Try V2 backend (newer versions)
                    from docling.backend.docling_parse_backend import DoclingParseV2DocumentBackend
                    backend = DoclingParseV2DocumentBackend
                    backend_name = "DoclingParseV2"
                except ImportError:
                    # Use default backend
                    pass

            # Configure pipeline options for performance
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = enable_ocr  # Disable OCR for speed (digital PDFs only)
            pipeline_options.do_table_structure = enable_table_structure  # Disable if no tables
            pipeline_options.generate_picture_images = enable_images  # Disable image extraction for speed

            # Use optimized PDF backend if available
            if backend:
                self.converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=pipeline_options,
                            backend=backend
                        )
                    }
                )
            else:
                # Fallback: use default backend with pipeline options
                self.converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=pipeline_options
                        )
                    }
                )

            logger.info(f"Docling converter initialized (OCR={enable_ocr}, Tables={enable_table_structure}, Images={enable_images}, Backend={backend_name})")
        except ImportError as e:
            logger.error(f"Failed to import Docling: {e}")
            self.converter = None

    def detect_format(self, file_path: Path) -> str:
        """Detect document format from file extension"""
        extension = file_path.suffix.lower()
        format_map = {
            '.pdf': 'pdf',
            '.docx': 'docx',
            '.doc': 'doc',
            '.html': 'html',
            '.htm': 'html',
            '.pptx': 'pptx',
            '.ppt': 'ppt',
            '.xlsx': 'xlsx',
            '.xls': 'xls',
            '.rtf': 'rtf',
            '.odt': 'odt',
            '.md': 'markdown',
        }
        return format_map.get(extension, 'unknown')

    def count_words(self, text: str) -> int:
        """Count words in text"""
        return len(text.split())

    def convert_to_markdown(
        self,
        file_path: Path,
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Convert document to markdown

        Args:
            file_path: Path to document file
            options: Conversion options

        Returns:
            Dictionary with markdown content and metadata
        """
        if options is None:
            options = {}

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect format
        doc_format = self.detect_format(file_path)
        logger.info(f"Converting {doc_format} file: {file_path.name}")

        # Get file size
        file_size = file_path.stat().st_size

        try:
            if self.converter is None:
                # Fallback: return mock conversion for testing
                logger.warning("Docling not available, using MOCK conversion")
                import hashlib
                file_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]

                markdown_content = f"""# Converted Document: {file_path.name}

This is a **MOCK conversion** for testing purposes (Docling not available).

## Document Information

- **File**: {file_path.name}
- **Format**: {doc_format.upper()}
- **Size**: {file_size / 1024:.2f} KB
- **Hash**: `{file_hash}`

## Content

Lorem ipsum dolor sit amet, consectetur adipiscing elit. This is placeholder
text representing the extracted content from the document.

### Section 1

Sample content that would be extracted from the real document.

### Section 2

More sample content demonstrating the conversion output.

**Note**: This is a mock conversion. In production, real content will be
extracted using Docling.
"""
            else:
                # Use Docling for conversion
                result = self.converter.convert(str(file_path))
                markdown_content = result.document.export_to_markdown()

                logger.info(f"Conversion successful: {len(markdown_content)} characters")

            # Extract metadata
            metadata = {
                "pages": None,  # Docling may provide this
                "words": self.count_words(markdown_content),
                "format": doc_format,
                "size_bytes": file_size,
                "title": file_path.stem,
                "author": None,
            }

            return {
                "markdown": markdown_content,
                "metadata": metadata,
            }

        except Exception as e:
            logger.error(f"Conversion failed: {e}", exc_info=True)
            raise Exception(f"Failed to convert document: {str(e)}")


# Global instance
_converter: DoclingConverter = None


def get_converter(preset: str = None) -> DoclingConverter:
    """
    Get or create converter instance with settings from config or preset

    Args:
        preset: Optional preset name ('fast', 'balanced', 'quality')
                If None, uses config defaults

    Returns:
        DoclingConverter instance
    """
    from shared.config import get_settings
    settings = get_settings()

    # Determine settings based on preset or config
    if preset == "fast":
        enable_ocr = False
        enable_images = False
        enable_table_structure = True
    elif preset == "balanced":
        enable_ocr = False
        enable_images = True
        enable_table_structure = True
    elif preset == "quality":
        enable_ocr = True
        enable_images = True
        enable_table_structure = True
    else:
        # Use config defaults
        enable_ocr = settings.docling_enable_ocr
        enable_images = settings.docling_enable_images
        enable_table_structure = settings.docling_enable_table_structure

    # Always create new instance for different presets
    return DoclingConverter(
        enable_ocr=enable_ocr,
        enable_table_structure=enable_table_structure,
        enable_images=enable_images,
    )
