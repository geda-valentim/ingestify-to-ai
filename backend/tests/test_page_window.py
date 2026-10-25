"""markdown_by_page: per-page Markdown from provenance, remapped to absolute pages."""
import pytest

pytest.importorskip("docling_core")
from docling_core.types.doc import (  # noqa: E402
    BoundingBox, CoordOrigin, DocItemLabel, DoclingDocument, ProvenanceItem, Size,
)

from workers.page_window import markdown_by_page  # noqa: E402


def _prov(page_no):
    return ProvenanceItem(page_no=page_no, charspan=(0, 1),
                          bbox=BoundingBox(l=0, t=10, r=10, b=0, coord_origin=CoordOrigin.BOTTOMLEFT))


def _doc(pages=3):
    doc = DoclingDocument(name="d")
    for n in range(1, pages + 1):
        doc.add_page(page_no=n, size=Size(width=100, height=100))
    return doc


def test_remaps_local_pages_to_absolute():
    doc = _doc(2)
    doc.add_text(label=DocItemLabel.TEXT, text="alpha", prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="beta", prov=_prov(2))
    out = markdown_by_page(doc, page_offset=4, page_count=2)
    assert list(out) == [5, 6]
    assert out[5] == "alpha" and out[6] == "beta"


def test_zero_offset_keeps_numbers():
    doc = _doc(1)
    doc.add_text(label=DocItemLabel.TEXT, text="alpha", prov=_prov(1))
    assert markdown_by_page(doc, page_count=1) == {1: "alpha"}


def test_page_without_items_is_empty():
    doc = _doc(3)
    doc.add_text(label=DocItemLabel.TEXT, text="alpha", prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="gamma", prov=_prov(3))
    out = markdown_by_page(doc, page_count=3)
    assert out[2] == ""
    assert out[1] == "alpha" and out[3] == "gamma"


def test_item_without_prov_is_in_no_page():
    doc = _doc(1)
    doc.add_text(label=DocItemLabel.TEXT, text="alpha", prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="orphan")
    out = markdown_by_page(doc, page_count=1)
    assert "orphan" not in "".join(out.values())
    assert out[1] == "alpha"


def test_export_kwargs_are_forwarded():
    doc = _doc(1)
    doc.add_text(label=DocItemLabel.TEXT, text="a_b", prov=_prov(1))
    assert markdown_by_page(doc, page_count=1)[1] == "a\\_b"
    assert markdown_by_page(doc, page_count=1, escape_underscores=False)[1] == "a_b"


def test_page_no_kwarg_is_rejected():
    with pytest.raises(TypeError):
        markdown_by_page(_doc(1), page_count=1, page_no=1)
