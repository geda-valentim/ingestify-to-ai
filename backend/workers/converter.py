import os
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class DoclingConverter:
    """Wrapper for Docling document converter"""

    def __init__(self, enable_ocr: bool = False, enable_table_structure: bool = True, enable_images: bool = False, pipeline_options: Dict[str, Any] = None):
        """
        Initialize Docling converter with optimizations

        Args:
            enable_ocr: Enable OCR for scanned documents (slower, disable for digital PDFs)
            enable_table_structure: Enable table structure recognition (disable if no tables needed)
            enable_images: Enable image extraction and processing (slower, disable for text-only conversion)
        """
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption, InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions, ConvertPipelineOptions
            from docling.document_converter import _get_default_option, ImageFormatOption
            from importlib.metadata import version

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
            from shared.document_capabilities import native_catalog
            if any(version(package) != native_catalog()[key] for package, key in
                   [('docling', 'docling_version'), ('docling-core', 'docling_core_version')]):
                raise RuntimeError('Docling capability catalog is stale; regenerate it with the worker version')
            configuration = dict(pipeline_options or {})
            from shared.document_capabilities import native_catalog
            import docling.datamodel.pipeline_options as native_options
            for field, classes in native_catalog()['pipeline_option_classes'].items():
                if field not in configuration:
                    continue
                values = dict(configuration[field])
                kind = values.pop('kind', 'default') if classes.keys() != {'default'} else 'default'
                cls = getattr(native_options, classes[kind])
                if isinstance(values.get('engine_options'), dict):
                    import importlib
                    engine_values = values['engine_options']
                    family = 'BaseImageClassificationEngineOptions' if field == 'picture_classification_options' else 'BaseVlmEngineOptions'
                    engine = native_catalog().get('engine_option_classes', {}).get(family, {}).get(engine_values.get('engine_type'))
                    if engine:
                        values['engine_options'] = getattr(importlib.import_module(engine['module']), engine['class']).model_validate(engine_values)
                configuration[field] = cls.model_validate(values)
            pipeline_options = PdfPipelineOptions(**configuration)
            pipeline_options.do_ocr = enable_ocr  # Disable OCR for speed (digital PDFs only)
            pipeline_options.do_table_structure = enable_table_structure  # Disable if no tables
            pipeline_options.generate_picture_images = enable_images  # Disable image extraction for speed

            # Pin the accelerator explicitly. Docling's own default is
            # device="auto", which resolves to cuda:0 whenever a GPU is visible
            # -- in every worker process at once, each with its own CUDA context
            # and layout/table weights, and with nothing logged. Passing the
            # value here makes the decision ours and visible; note that a
            # pydantic-settings init kwarg outranks the environment, so
            # DOCLING_DEVICE is ignored from now on in favour of DEVICE.
            self._apply_accelerator_options(pipeline_options)

            pdf_format = PdfFormatOption(pipeline_options=pipeline_options, **({'backend': backend} if backend else {}))
            format_options = {InputFormat.PDF: pdf_format, InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options)}
            # Simple pipelines support the shared enrichment controls too.
            # PDF OCR/layout/table controls remain specific to PDF/image input.
            shared_options = ConvertPipelineOptions(**{key: getattr(pipeline_options, key) for key in ConvertPipelineOptions.model_fields})
            for input_format in InputFormat:
                if input_format in format_options or input_format == InputFormat.AUDIO:
                    continue
                option = _get_default_option(input_format)
                if option.pipeline_cls.__name__ == 'SimplePipeline':
                    option.pipeline_options = shared_options
                    format_options[input_format] = option
            self.converter = DocumentConverter(format_options=format_options)

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
                raise RuntimeError("Docling não está instalado no worker")
            configuration = options.get('document_options') or {}
            conversion_arguments = {key: configuration[key] for key in
                ('page_range', 'max_num_pages', 'max_file_size', 'raises_on_error') if configuration.get(key) is not None}
            result = self.converter.convert(str(file_path), **conversion_arguments)
            from workers.document_outputs import export_document
            from shared.document_capabilities import native_catalog
            outputs = export_document(result.document, options, file_path.parent / 'document_assets')
            markdown_content = outputs['markdown']
            logger.info("Conversion successful: %s characters", len(markdown_content))

            # Extract metadata
            metadata = {
                "pages": len(result.document.pages) or None,
                "words": self.count_words(markdown_content),
                "format": doc_format,
                "size_bytes": file_size,
                "title": file_path.stem,
                "author": None,
                "provider": "docling", "model": native_catalog()['docling_version'],
                "output_format": configuration.get('output_format', 'markdown'),
                "available_formats": list(outputs['exports']), "configuration": options.get('document_options'),
            }

            return {
                **outputs,
                "metadata": metadata,
            }

        except Exception as e:
            logger.error(f"Conversion failed: {e}", exc_info=True)
            raise Exception(f"Failed to convert document: {str(e)}")


# Global instance
_converter: DoclingConverter = None


def get_converter(preset: str = None, pipeline_options: Dict[str, Any] = None) -> DoclingConverter:
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

    if pipeline_options is not None:
        enable_ocr = pipeline_options.get('do_ocr', enable_ocr)
        enable_table_structure = pipeline_options.get('do_table_structure', enable_table_structure)
        enable_images = pipeline_options.get('generate_picture_images', enable_images)
        return _cached_converter(enable_ocr, enable_table_structure, enable_images,
                                 json.dumps(pipeline_options, sort_keys=True, separators=(',', ':')))
    return _cached_converter(enable_ocr, enable_table_structure, enable_images)


# One converter per option set and process: building one loads docling's layout
# and table models (onto the GPU when DEVICE=cuda), so a fresh instance per task
# reloaded the weights for every page. Two slots cover a preset plus the default
# without letting every combination pile up in VRAM.
@lru_cache(maxsize=2)
def _cached_converter(enable_ocr: bool, enable_table_structure: bool, enable_images: bool, pipeline_key: str = "") -> DoclingConverter:
    extra = {"pipeline_options": json.loads(pipeline_key)} if pipeline_key else {}
    return DoclingConverter(
        **extra,
        enable_ocr=enable_ocr,
        enable_table_structure=enable_table_structure,
        enable_images=enable_images,
    )
