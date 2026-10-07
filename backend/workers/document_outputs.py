"""Native document exports and private, durable artifacts for main/page jobs."""
import json
import inspect
from pathlib import Path

from shared.document_capabilities import native_catalog
from shared.minio_client import get_minio_client

from shared.document_results import CONTENT_TYPES, result_object


def preserve_source_page_numbers(document, numbers):
    """Concatenation renumbers pages; export filters refer to original PDF pages."""
    mapping = dict(zip(sorted(document.pages), numbers, strict=True))
    for item, _ in document.iterate_items(with_groups=True):
        for provenance in getattr(item, 'prov', []):
            provenance.page_no = mapping[provenance.page_no]
    pages = {}
    for old, page in document.pages.items():
        page.page_no = mapping[old]
        pages[page.page_no] = page
    document.pages = pages
    return document


def export_document(document, options, assets_dir: Path):
    from shared.docling_catalog_generator import export_model
    configuration = options.get('document_options') or {}
    formats = configuration.get('formats', ['markdown'])
    export_options = configuration.get('export_options', {})
    outputs = {}
    # A canonical copy is always kept for merge/recovery, independent of JSON
    # export filters and precision selected by the user.
    canonical = document._with_embedded_pictures()
    for fmt in dict.fromkeys(['markdown', *formats]):
        method = native_catalog()['exports'][fmt]['method']
        arguments = export_model(type(document), 'export_to_doctags' if fmt == 'document_tokens' else method).model_validate(export_options.get(fmt, {})).model_dump()
        exported_document = canonical
        if arguments.get('image_mode') == 'referenced':
            prefix = options['_asset_url_prefix'].rstrip('/') + '/'
            if 'image_dir' in inspect.signature(getattr(canonical, method)).parameters:
                arguments.update(image_dir=assets_dir, image_uri_prefix=prefix)
            else:
                exported_document = canonical._with_pictures_refs(assets_dir, page_no=None, uri_prefix=prefix)
        content = getattr(exported_document, method)(**arguments)
        outputs[fmt] = json.dumps(content, ensure_ascii=False, indent=2) if isinstance(content, dict) else content
    assets = [{'name': path.name, '_local_path': str(path), 'content_type': 'image/png',
               'url': options['_asset_url_prefix'].rstrip('/') + '/' + path.name}
              for path in sorted(assets_dir.glob('*.png'))] if assets_dir.exists() else []
    return {'markdown': outputs['markdown'], 'exports': {fmt: outputs[fmt] for fmt in formats},
            'document': canonical.export_to_dict(), 'assets': assets}


def store_document_result(job_id, result, *, page_number=None):
    """Completion requires persistence; Redis and Elasticsearch are only caches."""
    storage = get_minio_client()
    directory = f'results/{job_id}/' + (f'page_{page_number:04d}/' if page_number is not None else '')
    for asset in result.get('assets', []):
        path = asset.get('_local_path')
        if path is not None:
            asset['object_name'] = directory + 'assets/' + asset['name']
            if not storage.upload_file(bucket_name=storage.bucket_results, object_name=asset['object_name'],
                                       file_path=path, content_type=asset['content_type']):
                raise RuntimeError(f'Document asset was not persisted: {asset["name"]}')
            asset.pop('_local_path', None)
    object_name = result_object(job_id, page_number)
    if not storage.upload_file(bucket_name=storage.bucket_results, object_name=object_name,
                               file_data=json.dumps(result, ensure_ascii=False).encode(), content_type='application/json'):
        raise RuntimeError(f'Document result was not persisted for {job_id}')
    return object_name


def load_document_result(job_id, *, page_number=None):
    storage = get_minio_client()
    return json.loads(storage.download_file(storage.bucket_results, result_object(job_id, page_number)))
