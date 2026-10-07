"""Generate lightweight API schemas from the Docling version installed in a worker.

Run: python -m shared.docling_catalog_generator [--check]
Never imported by API handlers: pipeline_options imports torch in Docling 2.87.
"""
import argparse
import copy
import inspect
import json
from importlib.metadata import version
from pathlib import Path
from typing import get_type_hints


def export_model(document_class, name):
    from pydantic import ConfigDict, create_model
    method = getattr(document_class, name)
    hints = get_type_hints(method)
    fields = {}
    for key, parameter in inspect.signature(method).parameters.items():
        if key in {'self', 'image_dir', 'image_uri_prefix'} or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        fields[key] = (hints.get(key, str), parameter.default if parameter.default is not inspect.Parameter.empty else ...)
    return create_model('Export' + ''.join(word.title() for word in name.removeprefix('export_to_').split('_')),
                        __config__=ConfigDict(extra='forbid'), **fields)


def catalog():
    import docling.datamodel.pipeline_options as native
    from docling.datamodel.base_models import FormatToExtensions, InputFormat
    from docling_core.types.doc import DoclingDocument
    from pydantic import BaseModel
    defaults = native.PdfPipelineOptions()
    schema = native.PdfPipelineOptions.model_json_schema()
    schema['additionalProperties'] = False
    definitions = schema.setdefault('$defs', {})
    concrete_classes = {}
    engine_classes = {}
    for field, value in defaults.__dict__.items():
        if not field.endswith('_options') or not isinstance(value, BaseModel):
            continue
        family = native.OcrOptions if field == 'ocr_options' else native.PictureDescriptionBaseOptions if field == 'picture_description_options' else type(value)
        choices = [cls for _, cls in inspect.getmembers(native, inspect.isclass)
                   if issubclass(cls, family) and getattr(cls, 'kind', None)]
        if not choices:
            choices = [type(value)]
        references, classes = [], {}
        for cls in sorted(set(choices), key=lambda c: c.__name__):
            item = cls.model_json_schema()
            definitions.update(item.pop('$defs', {}))
            kind = getattr(cls, 'kind', None)
            item['additionalProperties'] = False
            if kind:
                item['properties']['kind'] = {'type': 'string', 'const': kind, 'title': 'Engine', 'default': kind}
                classes[kind] = cls.__name__
            definitions[cls.__name__] = item
            references.append({'$ref': '#/$defs/' + cls.__name__})
        field_schema = copy.deepcopy(schema['properties'][field])
        field_schema.pop('$ref', None)
        field_schema.pop('anyOf', None)
        field_schema['anyOf'] = references
        field_schema['default'] = value.model_dump(mode='json')
        default_kind = getattr(type(value), 'kind', None)
        if default_kind:
            field_schema['default']['kind'] = default_kind
        schema['properties'][field] = field_schema
        concrete_classes[field] = classes or {'default': type(value).__name__}
    # Native pipeline annotations use base engine types. Expand those to the
    # concrete public options so quantization/compilation/VLM controls survive.
    import importlib
    for module_name, base_name in [('docling.datamodel.vlm_engine_options', 'BaseVlmEngineOptions'),
                                   ('docling.datamodel.image_classification_engine_options', 'BaseImageClassificationEngineOptions')]:
        module = importlib.import_module(module_name)
        base = getattr(module, base_name)
        references, classes = [], {}
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls is base or not issubclass(cls, base):
                continue
            item = cls.model_json_schema()
            definitions.update(item.pop('$defs', {}))
            engine_type = item['properties']['engine_type']['default']
            item['additionalProperties'] = False
            item['properties']['engine_type'].update(type='string', const=engine_type)
            item['properties']['engine_type'].pop('$ref', None)
            definitions[name] = item
            references.append({'$ref': '#/$defs/' + name})
            classes[engine_type] = {'module': module_name, 'class': name}
        engine_classes[base_name] = classes
        for definition in list(definitions.values()):
            field = definition.get('properties', {}).get('engine_options')
            if field and field.get('$ref') == '#/$defs/' + base_name:
                field.pop('$ref')
                field['anyOf'] = references
    exports = {}
    for name in sorted(dir(DoclingDocument)):
        if not name.startswith('export_to_'):
            continue
        format_name = name.removeprefix('export_to_')
        exports['json' if format_name == 'dict' else 'txt' if format_name == 'text' else format_name] = {
            'method': name,
            'parameters_schema': export_model(DoclingDocument, 'export_to_doctags' if name == 'export_to_document_tokens' else name).model_json_schema(),
        }
    return {'docling_version': version('docling'), 'docling_core_version': version('docling-core'),
            'image_extensions': FormatToExtensions[InputFormat.IMAGE],
            'pipeline_schema': schema, 'pipeline_option_classes': concrete_classes, 'engine_option_classes': engine_classes, 'exports': exports,
            'server_managed': ['artifacts_path', 'accelerator_options', 'enable_remote_services', 'allow_external_plugins'],
            'server_managed_export_parameters': ['image_dir', 'image_uri_prefix']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--stdout', action='store_true', help='Emit JSON for read-only worker mounts')
    args = parser.parse_args()
    target = Path(__file__).with_name('docling_catalog.json')
    content = json.dumps(catalog(), ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if args.stdout:
        print(content, end='')
        return
    if args.check:
        if not target.exists() or target.read_text() != content:
            raise SystemExit('Docling capability schemas are stale; regenerate with the installed worker version')
    else:
        target.write_text(content)
    print(('Checked' if args.check else 'Generated') + ' Docling pipeline and export schemas')


if __name__ == '__main__':
    main()
