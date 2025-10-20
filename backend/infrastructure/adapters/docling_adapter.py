"""
Docling Converter Adapter - Implementa ConverterPort

Adapta Docling para a interface ConverterPort definida na Application layer
"""
import logging
from pathlib import Path
from typing import Dict, Any

from application.ports.converter_port import ConverterPort, ConversionResult, ConversionError

logger = logging.getLogger(__name__)


class DoclingConverterAdapter(ConverterPort):
    """
    Adapter para Docling

    Implementa ConverterPort usando Docling como motor de conversão
    """

    def __init__(self, enable_ocr: bool = False, enable_table_structure: bool = True):
        """
        Inicializa adapter

        Args:
            enable_ocr: Habilitar OCR (mais lento)
            enable_table_structure: Habilitar reconhecimento de tabelas
        """
        self.enable_ocr = enable_ocr
        self.enable_table_structure = enable_table_structure
        self.converter = self._initialize_docling()

    def _initialize_docling(self):
        """Inicializa Docling com configurações"""
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption, InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions

            # Pipeline options
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = self.enable_ocr
            pipeline_options.do_table_structure = self.enable_table_structure

            # Try optimized backend
            backend = None
            backend_name = "default"
            try:
                from docling.backend.docling_parse_backend import DoclingParseV2DocumentBackend
                backend = DoclingParseV2DocumentBackend
                backend_name = "DoclingParseV2"
            except ImportError:
                try:
                    from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
                    backend = DoclingParseDocumentBackend
                    backend_name = "DoclingParse"
                except ImportError:
                    pass

            # Create converter
            if backend:
                converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=pipeline_options,
                            backend=backend
                        )
                    }
                )
            else:
                converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=pipeline_options
                        )
                    }
                )

            logger.info(
                f"Docling initialized (OCR={self.enable_ocr}, "
                f"Tables={self.enable_table_structure}, Backend={backend_name})"
            )

            return converter

        except ImportError as e:
            logger.warning(f"Docling not available: {e}")
            return None

    async def convert_to_markdown(
        self,
        file_path: Path,
        options: Dict[str, Any] = None
    ) -> ConversionResult:
        """
        Converte documento para Markdown usando Docling

        Args:
            file_path: Path to document
            options: Conversion options

        Returns:
            ConversionResult

        Raises:
            ConversionError: Se conversão falhar
        """
        if options is None:
            options = {}

        if not file_path.exists():
            raise ConversionError(f"File not found: {file_path}")

        logger.info(f"Converting document: {file_path.name}")

        try:
            if self.converter is None:
                # Fallback: mock conversion for testing
                logger.warning("Docling not available, using mock conversion")
                markdown = self._mock_conversion(file_path)
            else:
                # Real Docling conversion
                result = self.converter.convert(str(file_path))
                markdown = result.document.export_to_markdown()

            # Extract metadata
            file_size = file_path.stat().st_size
            word_count = len(markdown.split())

            metadata = {
                "format": self._detect_format_string(file_path),
                "size_bytes": file_size,
                "words": word_count,
                "pages": None,  # Docling may provide this
                "title": file_path.stem,
                "author": None,
            }

            logger.info(
                f"Conversion successful: {len(markdown)} chars, {word_count} words"
            )

            return ConversionResult(
                markdown=markdown,
                metadata=metadata
            )

        except Exception as e:
            logger.error(f"Conversion failed for {file_path}: {e}", exc_info=True)
            raise ConversionError(f"Failed to convert document: {str(e)}")

    async def detect_format(self, file_path: Path) -> str:
        """
        Detecta formato do documento

        Args:
            file_path: Path to file

        Returns:
            Format string (pdf, docx, html, etc.)
        """
        return self._detect_format_string(file_path)

    async def is_supported(self, file_path: Path) -> bool:
        """
        Verifica se formato é suportado

        Args:
            file_path: Path to file

        Returns:
            True se suportado
        """
        supported_extensions = [
            '.pdf', '.docx', '.doc', '.html', '.htm',
            '.pptx', '.ppt', '.xlsx', '.xls', '.rtf', '.odt'
        ]
        return file_path.suffix.lower() in supported_extensions

    # ============================================
    # Helper methods
    # ============================================

    def _detect_format_string(self, file_path: Path) -> str:
        """Detecta formato por extensão"""
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
        }
        return format_map.get(extension, 'unknown')

    def _mock_conversion(self, file_path: Path) -> str:
        """Conversão mock para testes (quando Docling não disponível)"""
        import hashlib
        file_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]

        return f"""# Converted Document: {file_path.name}

This is a **MOCK conversion** for testing purposes (Docling not available).

## Document Information

- **File**: {file_path.name}
- **Format**: {self._detect_format_string(file_path).upper()}
- **Size**: {file_path.stat().st_size / 1024:.2f} KB
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
