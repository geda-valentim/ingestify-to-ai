import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class DoclingConverter:
    """Wrapper for Docling document converter"""

    def __init__(self, enable_ocr: bool = False, enable_table_structure: bool = True, enable_images: bool = False,
                 picture_images: bool = False):
        """
        Initialize Docling converter with optimizations

        Args:
            enable_ocr: Enable OCR for scanned documents (slower, disable for digital PDFs)
            enable_table_structure: Enable table structure recognition (disable if no tables needed)
            enable_images: Enable image extraction and processing (slower, disable for text-only conversion)
            picture_images: image_mode=referenced: picture crops are generated (whatever
                enable_images says) at CONVERSION_IMAGES_SCALE. Only this flag changes
                the scale, so image_mode=none costs and converts exactly as before.
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
            pipeline_options.generate_picture_images = enable_images or picture_images  # Disable image extraction for speed
            if picture_images:
                # Resolution of the stored picture assets (image_mode=referenced only)
                from shared.config import get_settings
                pipeline_options.images_scale = float(get_settings().conversion_images_scale)

            # Pin the accelerator explicitly. Docling's own default is
            # device="auto", which resolves to cuda:0 whenever a GPU is visible
            # -- in every worker process at once, each with its own CUDA context
            # and layout/table weights, and with nothing logged. Passing the
            # value here makes the decision ours and visible; note that a
            # pydantic-settings init kwarg outranks the environment, so
            # DOCLING_DEVICE is ignored from now on in favour of DEVICE.
            self._apply_accelerator_options(pipeline_options)

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

    @staticmethod
    def _apply_accelerator_options(pipeline_options) -> None:
        """
        Set pipeline_options.accelerator_options from DEVICE / DOCLING_NUM_THREADS.

        Logged once per converter construction: the resolved device is the one
        piece of information missing from every "Failed to convert document"
        report today.

        A *docling* failure here must never stop the conversion: an older
        docling that does not expose AcceleratorOptions still converts, it just
        keeps its own device default. A DEVICE misconfiguration is different and
        is deliberately NOT swallowed -- an explicit DEVICE=cuda that cannot be
        satisfied is a hard error, never a silent downgrade.
        """
        from shared.config import get_settings
        from shared.device import resolve_docling_device

        settings = get_settings()
        num_threads = settings.docling_num_threads
        device = resolve_docling_device()  # may raise DeviceUnavailableError

        try:
            try:
                from docling.datamodel.accelerator_options import AcceleratorOptions
            except ImportError:
                # Older docling re-exports it from pipeline_options.
                from docling.datamodel.pipeline_options import AcceleratorOptions

            pipeline_options.accelerator_options = AcceleratorOptions(
                device=device,
                num_threads=num_threads,
            )
            logger.info(
                "Docling accelerator: device=%s num_threads=%s", device, num_threads
            )
        except Exception as e:
            logger.warning(
                "Could not set docling accelerator options (%s); "
                "docling will use its own device default",
                e,
            )

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
        options: Dict[str, Any] = None,
        assets=None,
        figures=None,
    ) -> Dict[str, Any]:
        """
        Convert document to markdown

        Args:
            file_path: Path to document file
            options: Conversion options (`image_mode`, `page_images`: image assets)
            assets: A workers.image_assets.AssetCollector when the job asked for
                image assets; None keeps today's output exactly.
            figures: A workers.image_assets.FigureCollector when the job asked for
                describe_images / ocr_images (the result then carries `figures`,
                the entries the describe stage works from)

        Returns:
            Dictionary with markdown content and metadata (and `assets` /
            `assets_skipped` when `assets` was given)
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
                referenced = assets is not None and options.get("image_mode") == "referenced"
                if referenced or figures is not None:
                    from workers.image_assets import extract_pictures
                    markdown_content = extract_pictures(result.document, assets if referenced else None, figures)
                else:
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

            converted = {
                "markdown": markdown_content,
                "metadata": metadata,
            }
            if assets is not None:
                if options.get("page_images") is True and doc_format == "pdf":
                    from workers.image_assets import render_pages
                    render_pages(file_path, assets)
                converted.update(assets.result_fields())
            if figures is not None:
                converted.update(figures.result_fields())
            return converted

        except Exception as e:
            logger.error(f"Conversion failed: {e}", exc_info=True)
            raise Exception(f"Failed to convert document: {str(e)}")


# Global instance
_converter: DoclingConverter = None


def get_converter(preset: str = None, picture_images: bool = False) -> DoclingConverter:
    """
    Get or create converter instance with settings from config or preset

    Args:
        preset: Optional preset name ('fast', 'balanced', 'quality')
                If None, uses config defaults
        picture_images: image_mode=referenced (and describe_images / ocr_images)
                need docling's picture crops (generate_picture_images) whatever
                the preset says

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

    if picture_images:
        return _cached_converter(enable_ocr, enable_table_structure, enable_images, True)
    return _cached_converter(enable_ocr, enable_table_structure, enable_images)


# One converter per option set and process: building one loads docling's layout
# and table models (onto the GPU when DEVICE=cuda), so a fresh instance per task
# reloaded the weights for every page. Two slots cover a preset plus the default
# without letting every combination pile up in VRAM. picture_images
# (image_mode=referenced) is part of the key: its crops use another images_scale.
@lru_cache(maxsize=2)
def _cached_converter(enable_ocr: bool, enable_table_structure: bool, enable_images: bool,
                      picture_images: bool = False) -> DoclingConverter:
    options = dict(enable_ocr=enable_ocr, enable_table_structure=enable_table_structure, enable_images=enable_images)
    if picture_images:
        options["picture_images"] = True
    return DoclingConverter(**options)
