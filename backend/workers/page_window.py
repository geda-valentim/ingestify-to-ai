"""Per-page Markdown export from a DoclingDocument's provenance (inert helper, no callers yet).

Page convention (same as ``AssetCollector.absolute_page`` in workers/image_assets.py):
a window converted from a split page has ``page_offset = page_number - 1`` and the
document's own page numbers are local (1-based), so the absolute page is
``local + page_offset``. For a whole document ``page_offset`` is 0 and nothing changes.
"""
from typing import Any, Dict


def markdown_by_page(doc, *, page_offset: int = 0, page_count: int, **export_kwargs: Any) -> Dict[int, str]:
    """Return ``{absolute_page: markdown}`` for local pages 1..page_count.

    Uses ``doc.export_to_markdown(page_no=k)``, which keeps only items whose provenance
    lies on page k; a page without items yields "" and items without provenance appear
    in no page. ``export_kwargs`` are passed through to every export call (``page_no`` is
    reserved).
    """
    if "page_no" in export_kwargs:
        raise TypeError("page_no is set per page by markdown_by_page")
    offset = int(page_offset or 0)
    return {
        offset + local: doc.export_to_markdown(page_no=local, **export_kwargs)
        for local in range(1, int(page_count) + 1)
    }
