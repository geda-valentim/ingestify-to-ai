"""PDFs that qpdf repairs with warnings (exit status 3) must split, not fail (2026-10-08)."""
import subprocess
from pathlib import Path

import pytest

from shared import pdf_splitter
from tests import _pdf_samples as S

qpdf_available = subprocess.run(["which", "qpdf"], capture_output=True).returncode == 0


def _damaged_pdf(tmp_path: Path) -> Path:
    """A two-page PDF whose startxref points nowhere: qpdf rebuilds the xref and warns."""
    data = S.pdf([S.text_page("Pagina um"), S.text_page("Pagina dois")])
    cut = data.rfind(b"startxref")
    path = tmp_path / "damaged.pdf"
    path.write_bytes(data[:cut] + b"startxref\n999999\n%%EOF\n")
    return path


@pytest.mark.skipif(not qpdf_available, reason="qpdf not installed")
def test_qpdf_really_exits_3_on_this_fixture(tmp_path):
    path = _damaged_pdf(tmp_path)
    assert subprocess.run(["qpdf", "--show-npages", str(path)], capture_output=True).returncode == 3


@pytest.mark.skipif(not qpdf_available, reason="qpdf not installed")
def test_a_damaged_pdf_splits_into_valid_pages(tmp_path, monkeypatch):
    path = _damaged_pdf(tmp_path)
    splitter = pdf_splitter.PDFSplitter(tmp_path / "pages")
    assert pdf_splitter.should_split_pdf(path, min_pages=2) is True
    pages = splitter.split_pdf(path, job_id=None, upload_to_minio=False)
    assert [n for n, _, _ in pages] == [1, 2]
    assert all(pdf_splitter._pypdf_page_count(p) == 1 for _, p, _ in pages)
    single, _ = splitter.extract_single_page(path, 2, upload_to_minio=False)
    assert pdf_splitter._pypdf_page_count(single) == 1


def test_pypdf2_fallback_when_qpdf_fails_outright(tmp_path, monkeypatch):
    path = tmp_path / "ok.pdf"
    path.write_bytes(S.pdf([S.text_page("A"), S.text_page("B"), S.text_page("C")]))

    def broken_qpdf(args):
        raise subprocess.CalledProcessError(2, ["qpdf"] + args, stderr="qpdf: boom")

    monkeypatch.setattr(pdf_splitter, "_qpdf", broken_qpdf)
    assert pdf_splitter.count_pages(path) == 3
    out = tmp_path / "p2.pdf"
    pdf_splitter.extract_page(path, 2, out)
    assert pdf_splitter._pypdf_page_count(out) == 1


def test_an_empty_extraction_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "ok.pdf"
    path.write_bytes(S.pdf([S.text_page("A"), S.text_page("B")]))
    monkeypatch.setattr(pdf_splitter, "_qpdf", lambda args: Path(args[-1]).write_bytes(b""))
    with pytest.raises(ValueError, match="PAGE_EXTRACTION_INVALID"):
        pdf_splitter.extract_page(path, 1, tmp_path / "p1.pdf")
