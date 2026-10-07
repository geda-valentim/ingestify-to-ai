"""Lightweight Docling request validation; native schemas are generated in workers."""
import copy
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DocumentFormat = Literal['markdown', 'json', 'html', 'txt', 'doclang', 'doctags', 'document_tokens', 'element_tree', 'vtt']
PRESETS = {
    'fast': {'do_ocr': False, 'do_table_structure': True, 'generate_picture_images': False},
    'balanced': {'do_ocr': False, 'do_table_structure': True, 'generate_picture_images': True},
    'quality': {'do_ocr': True, 'do_table_structure': True, 'generate_picture_images': True},
}


@lru_cache(maxsize=1)
def native_catalog():
    return json.loads(Path(__file__).with_name('docling_catalog.json').read_text())


def _resolve(schema, definitions, value):
    if '$ref' in schema:
        schema = definitions[schema['$ref'].rsplit('/', 1)[-1]]
    if 'anyOf' in schema:
        choices = [_resolve(choice, definitions, value) for choice in schema['anyOf']]
        if isinstance(value, dict):
            kind = value.get('kind')
            engine_type = value.get('engine_type')
            selected = next((choice for choice in choices if kind is not None and
                             choice.get('properties', {}).get('kind', {}).get('const') == kind), None)
            if selected:
                return selected
            selected = next((choice for choice in choices if engine_type is not None and choice.get('properties', {}).get('engine_type', {}).get('const') == engine_type), None)
            if selected:
                return selected
        return next((choice for choice in choices if Draft202012Validator({**choice, '$defs': definitions}).is_valid(value)), schema)
    return schema


def _defaults(value, schema, definitions):
    schema = _resolve(schema, definitions, value)
    if isinstance(value, dict):
        result = copy.deepcopy(value)
        for key, field in schema.get('properties', {}).items():
            if key not in result and 'default' in field:
                result[key] = copy.deepcopy(field['default'])
            if key in result:
                result[key] = _defaults(result[key], field, definitions)
        return result
    return value


def _merge_defaults(defaults, value):
    if not isinstance(defaults, dict) or not isinstance(value, dict):
        return copy.deepcopy(value)
    for discriminator in ('kind', 'engine_type'):
        if discriminator in value and value[discriminator] != defaults.get(discriminator):
            defaults = {}
            break
    return {**copy.deepcopy(defaults), **{key: _merge_defaults(defaults.get(key), item) for key, item in value.items()}}


def _validate(value, schema, name):
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        error = errors[0]
        path = '.'.join(str(part) for part in error.absolute_path)
        raise ValueError(f'{name}{"." + path if path else ""}: {error.message}')


def _policy(value, path='pipeline', *, explicit=True):
    """Filesystem, executables and remote code follow the service's policy."""
    if isinstance(value, dict):
        for key, item in value.items():
            if explicit and (key in native_catalog()['server_managed'] or key == 'tesseract_cmd' or
                             key in {'path', 'model_storage_directory'} or key.endswith('_path')):
                raise ValueError(f'{path}.{key} é configurado pelo servidor')
            if key == 'engine_type' and (str(item).startswith('api') or item == 'remote'):
                raise ValueError(f'{path}.{key}: serviços remotos estão desabilitados no servidor')
            if key == 'trust_remote_code' and item:
                raise ValueError(f'{path}.{key} não é permitido pela política do servidor')
            if key == 'kind' and item in {'api', 'kserve_v2_ocr'}:
                raise ValueError(f'{path}: serviços remotos Docling estão desabilitados no servidor')
            _policy(item, f'{path}.{key}', explicit=explicit)
    elif isinstance(value, list):
        for item in value:
            _policy(item, path, explicit=explicit)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f'{path}: número deve ser finito')


class DocumentOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    pipeline: dict[str, Any] = Field(default_factory=dict, description='Controles PdfPipelineOptions. Opções explícitas substituem o preset.')
    formats: list[DocumentFormat] = Field(default_factory=lambda: ['markdown'], min_length=1, max_length=9)
    output_format: DocumentFormat = 'markdown'
    export_options: dict[str, dict[str, Any]] = Field(default_factory=dict, description='Parâmetros nativos por formato; caminhos de imagens são geridos pelo servidor.')
    page_range: tuple[int, int] | None = Field(None, description='Primeira/última página inclusivas, numeradas a partir de 1.')
    max_num_pages: int | None = Field(None, ge=1)
    max_file_size: int | None = Field(None, ge=1, description='Limite da conversão em bytes, adicional ao limite de upload do serviço.')
    raises_on_error: bool = True

    @classmethod
    def model_json_schema(cls, **kwargs):
        schema = super().model_json_schema(**kwargs)
        schema['properties']['pipeline']['x-options-schema'] = native_catalog()['pipeline_schema']
        return schema

    @field_validator('page_range')
    @classmethod
    def page_interval(cls, value):
        if value is not None and (value[0] < 1 or value[1] < value[0]):
            raise ValueError('page_range deve ser [primeira, última], com 1 <= primeira <= última')
        return value

    @model_validator(mode='after')
    def validate_native_options(self):
        if len(set(self.formats)) != len(self.formats):
            raise ValueError('formats não pode repetir formatos')
        if self.output_format not in self.formats:
            raise ValueError('output_format deve estar em formats')
        _policy(self.pipeline)
        schema = native_catalog()['pipeline_schema']
        pipeline = copy.deepcopy(self.pipeline)
        for field, classes in native_catalog()['pipeline_option_classes'].items():
            if field in pipeline and isinstance(pipeline[field], dict) and classes.keys() != {'default'}:
                pipeline[field].setdefault('kind', schema['properties'][field]['default'].get('kind'))
        # Concrete native options often require their model/engine spec. A
        # partial override keeps the configured defaults for that same engine.
        pipeline = {key: _defaults(_merge_defaults(schema['properties'].get(key, {}).get('default'), value),
                    schema['properties'].get(key, {}), schema['$defs']) for key, value in pipeline.items()}
        _validate(pipeline, schema, 'pipeline')
        for key in ('ocr_batch_size', 'layout_batch_size', 'table_batch_size', 'queue_max_size'):
            if key in pipeline and not 1 <= pipeline[key] <= 1024:
                raise ValueError(f'pipeline.{key}: permitido entre 1 e 1024')
        for key in ('images_scale', 'batch_polling_interval_seconds', 'document_timeout'):
            if pipeline.get(key) is not None and pipeline[key] <= 0:
                raise ValueError(f'pipeline.{key} deve ser positivo')
        self.pipeline = pipeline
        for fmt, parameters in self.export_options.items():
            if fmt not in self.formats:
                raise ValueError(f'export_options.{fmt}: formato deve estar em formats')
            _validate(parameters, native_catalog()['exports'][fmt]['parameters_schema'], f'export_options.{fmt}')
        return self


def document_options(raw=None, preset='fast'):
    """Canonical resolved configuration for deduplication and durable dispatch."""
    if preset not in PRESETS:
        raise ValueError('docling_preset deve ser fast, balanced ou quality')
    if isinstance(raw, str):
        raw = json.loads(raw)
    request = raw if isinstance(raw, DocumentOptions) else DocumentOptions.model_validate(raw or {})
    pipeline = {**PRESETS[preset], **request.pipeline}
    schema = native_catalog()['pipeline_schema']
    pipeline = _defaults(pipeline, schema, schema['$defs'])
    for key in native_catalog()['server_managed']:
        pipeline.pop(key, None)
    # Generated native defaults may trust a bundled model; explicit clients may
    # never enable execution of a new repository's code.
    exports = {fmt: _defaults(request.export_options.get(fmt, {}), data['parameters_schema'], data['parameters_schema'].get('$defs', {}))
               for fmt, data in native_catalog()['exports'].items() if fmt in request.formats}
    return {'docling_preset': preset, 'docling_core_version': native_catalog()['docling_core_version'], 'document_options': {**request.model_dump(mode='json'), 'pipeline': pipeline, 'export_options': exports}}


def enrichment_requirements(pipeline):
    """Dependencies of enabled stages; unused engine settings do not load models."""
    requirements = set()
    stages = {
        'picture_classification_options': pipeline.get('do_picture_classification') or pipeline.get('do_chart_extraction'),
        'picture_description_options': pipeline.get('do_picture_description'),
        'code_formula_options': pipeline.get('do_code_enrichment') or pipeline.get('do_formula_enrichment'),
    }
    for name, enabled in stages.items():
        if enabled:
            options = pipeline.get(name, {}).get('engine_options', {})
            requirements.add(options.get('engine_type', 'transformers'))
            if options.get('quantized'):
                requirements.add('bitsandbytes')
    if pipeline.get('do_chart_extraction'):
        requirements.add('transformers')
    return requirements


def missing_enrichment_dependencies(pipeline, prerequisites):
    """Reject known absence while allowing workers with an older heartbeat."""
    requirements = enrichment_requirements(pipeline)
    if not prerequisites or not requirements:
        return []
    if any(all(worker.get('enrichment_dependencies', {}).get(name) is not False
               for name in requirements) for worker in prerequisites):
        return []
    return sorted(requirements)


def annotate_enrichment_availability(schema, prerequisites):
    for definition in schema.get('$defs', {}).values():
        properties = definition.get('properties', {})
        engine = properties.get('engine_type', {}).get('const')
        if engine and prerequisites and all(worker.get('enrichment_dependencies', {}).get(engine) is False
                                            for worker in prerequisites):
            definition['x-unavailable-reason'] = 'Dependência do engine ausente nos workers ativos'
        if 'quantized' in properties and prerequisites and all(
                worker.get('enrichment_dependencies', {}).get('bitsandbytes') is False for worker in prerequisites):
            properties['quantized']['enum'] = [False]
            properties['quantized']['description'] = 'Quantização indisponível: bitsandbytes ausente nos workers ativos.'


class DocumentCapabilities(BaseModel):
    provider: str = 'docling'
    version: str
    core_version: str
    image_extensions: list[str]
    pipeline_schema: dict
    exports: dict
    presets: dict
    server_managed: list[str]
    restrictions: list[str]
    workers_running: bool = False
    worker_prerequisites: list[dict] = Field(default_factory=list)


def document_capabilities():
    data = native_catalog()
    schema = copy.deepcopy(data['pipeline_schema'])
    for class_name in ('KserveV2OcrOptions', 'PictureDescriptionApiOptions'):
        schema['$defs'][class_name]['x-unavailable-reason'] = 'Serviços remotos desabilitados no servidor'
    for definition in schema.get('$defs', {}).values():
        engine = definition.get('properties', {}).get('engine_type', {}).get('const', '')
        if str(engine).startswith('api'):
            definition['x-unavailable-reason'] = 'Serviços remotos desabilitados no servidor'
        for name, field in definition.get('properties', {}).items():
            if name in {'path', 'tesseract_cmd', 'model_storage_directory'} or name.endswith('_path'):
                field['readOnly'] = True
    for field in data['server_managed']:
        schema['properties'][field]['readOnly'] = True
    return DocumentCapabilities(version=data['docling_version'], core_version=data['docling_core_version'],
        image_extensions=data['image_extensions'],
        pipeline_schema=schema, exports=data['exports'], presets=PRESETS, server_managed=data['server_managed'],
        restrictions=['Os caminhos, acelerador, plugins e serviços remotos são configurados pelo servidor.',
                      'Dependências OCR e modelos opcionais são verificados pelo worker ao executar; catálogo não confirma que seus pesos foram baixados.',
                      'Os controles de OCR/layout/tabelas da pipeline PDF aplicam-se a PDF e imagens de documento.'])
