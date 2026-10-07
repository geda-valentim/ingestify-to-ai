"""Worker-side prerequisites without loading torch or downloading models."""
import importlib.util
import os
import platform
import shutil
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from shared.document_capabilities import native_catalog


def _installed(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


@lru_cache(maxsize=1)
def worker_prerequisites():
    data = native_catalog()
    versions = {}
    for package in ('docling', 'docling-core'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    engines = {'easyocr': _installed('easyocr'), 'rapidocr': _installed('rapidocr'),
               'tesseract': bool(shutil.which('tesseract')), 'tesserocr': _installed('tesserocr'),
               'ocrmac': platform.system() == 'Darwin' and _installed('ocrmac'), 'kserve_v2_ocr': False}
    engines['auto'] = any(engines.values())
    transformers = all(_installed(module) for module in ('torch', 'transformers', 'accelerate'))
    enrichments = {'transformers': transformers, 'auto_inline': transformers,
                   'onnxruntime': _installed('onnxruntime') and _installed('transformers'),
                   'vllm': transformers and _installed('vllm'),
                   'mlx': platform.system() == 'Darwin' and _installed('mlx_vlm'),
                   'bitsandbytes': _installed('bitsandbytes')}
    return {'versions': versions, 'catalog_matches': versions['docling'] == data['docling_version'] and versions['docling-core'] == data['docling_core_version'],
            'ocr_dependencies': engines, 'enrichment_dependencies': enrichments,
            'automatic_model_downloads': os.environ.get('HF_HUB_OFFLINE', '').lower() not in {'1', 'true', 'yes'}}


def worker_readiness():
    data = native_catalog()
    cache = Path(os.environ.get('HF_HUB_CACHE') or (Path(os.environ.get('HF_HOME', Path.home() / '.cache' / 'huggingface')) / 'hub'))
    models = {}
    for name in ('picture_classification_options', 'picture_description_options', 'code_formula_options', 'chart_extraction_options'):
        defaults = data['pipeline_schema']['properties'][name].get('default', {})
        spec = defaults.get('model_spec', defaults)
        repo = spec.get('repo_id') or spec.get('default_repo_id')
        snapshots = cache / ('models--' + repo.replace('/', '--')) / 'snapshots' if repo else None
        weights = snapshots is not None and snapshots.exists() and any(path.suffix in {'.safetensors', '.onnx', '.bin'} for path in snapshots.rglob('*'))
        models[name] = {'repo_id': repo, 'default_weights_cached': bool(weights) if repo else None}
    return {**worker_prerequisites(), 'models': models}
