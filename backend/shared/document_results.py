"""Private document artifact keys and public export MIME types."""
CONTENT_TYPES = {'markdown': 'text/markdown', 'json': 'application/json', 'html': 'text/html',
                 'txt': 'text/plain', 'vtt': 'text/vtt', 'doclang': 'text/plain',
                 'doctags': 'text/plain', 'document_tokens': 'text/plain', 'element_tree': 'text/plain'}


def result_object(job_id, page_number=None):
    return f'results/{job_id}/' + (f'page_{page_number:04d}.document.json' if page_number is not None else 'document.json')
