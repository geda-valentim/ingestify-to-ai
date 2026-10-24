"""
A worker without Docling must fail the conversion, never complete it with placeholder text.

The converter used to answer a MOCK / Lorem ipsum Markdown when `docling` could not
be imported, so the job ended `completed` with fake content. It now raises, and the
task's usual failure path (retry, then `failed`) takes over.
"""

import sys

import pytest

from workers.converter import DoclingConverter
from workers.tasks import _convert


@pytest.fixture
def converter_without_docling(monkeypatch):
    # `None` in sys.modules makes the import raise ImportError whether or not docling is installed
    monkeypatch.setitem(sys.modules, "docling.document_converter", None)
    return DoclingConverter()


def test_convert_raises_instead_of_returning_a_mock(converter_without_docling, tmp_path):
    source = tmp_path / "a.docx"
    source.write_bytes(b"x")

    assert converter_without_docling.converter is None
    with pytest.raises(RuntimeError, match="Docling is not available in this worker: .*docling"):
        converter_without_docling.convert_to_markdown(source, {})


def test_the_task_helper_propagates_the_error_so_the_job_fails(converter_without_docling, tmp_path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF-1.4")

    with pytest.raises(RuntimeError, match="Docling is not available"):
        _convert(converter_without_docling, source, {}, None)
