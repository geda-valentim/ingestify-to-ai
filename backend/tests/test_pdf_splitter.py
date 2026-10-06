"""
Unit tests for shared.pdf_splitter.

should_split_pdf() gates the whole parallel-page pipeline: a wrong answer here
either serialises a 200-page PDF into one job or explodes a 1-page PDF into the
split/merge machinery for no reason.
"""

import subprocess
from pathlib import Path

import pytest

from shared.pdf_splitter import PDFSplitter, should_split_pdf


class _CompletedProcess:
    def __init__(self, stdout):
        self.stdout = stdout
        self.returncode = 0


def _stub_qpdf(monkeypatch, pages):
    """Make qpdf report `pages` pages without invoking the binary."""
    def fake_run(cmd, **kwargs):
        assert cmd[0] == "qpdf", f"expected a qpdf call, got {cmd!r}"
        return _CompletedProcess(f"{pages}\n")

    monkeypatch.setattr(subprocess, "run", fake_run)


class TestShouldSplitPdf:
    def test_non_pdf_is_never_split(self, monkeypatch, tmp_path):
        # Guard: qpdf must not even be consulted for a non-PDF.
        def explode(*a, **k):
            raise AssertionError("qpdf must not run for a non-PDF file")

        monkeypatch.setattr(subprocess, "run", explode)
        assert should_split_pdf(tmp_path / "doc.docx") is False

    @pytest.mark.parametrize("suffix", [".PDF", ".Pdf", ".pdf"])
    def test_extension_check_is_case_insensitive(self, monkeypatch, tmp_path, suffix):
        _stub_qpdf(monkeypatch, pages=5)
        assert should_split_pdf(tmp_path / f"doc{suffix}") is True

    def test_single_page_pdf_is_not_split(self, monkeypatch, tmp_path):
        _stub_qpdf(monkeypatch, pages=1)
        assert should_split_pdf(tmp_path / "doc.pdf") is False

    def test_page_count_equal_to_min_pages_is_split(self, monkeypatch, tmp_path):
        # Boundary: the check is >=, not >.
        _stub_qpdf(monkeypatch, pages=2)
        assert should_split_pdf(tmp_path / "doc.pdf", min_pages=2) is True

    def test_min_pages_threshold_is_respected(self, monkeypatch, tmp_path):
        _stub_qpdf(monkeypatch, pages=9)
        assert should_split_pdf(tmp_path / "doc.pdf", min_pages=10) is False

    def test_qpdf_failure_degrades_to_not_splitting(self, monkeypatch, tmp_path):
        """A broken/encrypted PDF must fall back to single-job conversion,
        never propagate an exception into the Celery task."""
        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(2, cmd, stderr="damaged file")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert should_split_pdf(tmp_path / "doc.pdf") is False

    def test_unparsable_qpdf_output_degrades_to_not_splitting(self, monkeypatch, tmp_path):
        monkeypatch.setattr(subprocess, "run", lambda cmd, **k: _CompletedProcess("not-a-number"))
        assert should_split_pdf(tmp_path / "doc.pdf") is False


class TestPDFSplitter:
    def test_init_creates_temp_dir(self, tmp_path):
        target = tmp_path / "nested" / "workdir"
        PDFSplitter(temp_dir=target)
        assert target.is_dir()

    def test_is_pdf(self, tmp_path):
        splitter = PDFSplitter(temp_dir=tmp_path)
        assert splitter.is_pdf(Path("a.pdf")) is True
        assert splitter.is_pdf(Path("a.PDF")) is True
        assert splitter.is_pdf(Path("a.docx")) is False
        assert splitter.is_pdf(Path("a")) is False

    def test_get_page_count(self, monkeypatch, tmp_path):
        _stub_qpdf(monkeypatch, pages=42)
        assert PDFSplitter(temp_dir=tmp_path).get_page_count(Path("a.pdf")) == 42

    def test_get_page_count_propagates_failure(self, monkeypatch, tmp_path):
        """Unlike should_split_pdf, an explicit page count must NOT be silently
        swallowed - the caller needs to know the PDF is unreadable."""
        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(2, cmd, stderr="damaged file")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(subprocess.CalledProcessError):
            PDFSplitter(temp_dir=tmp_path).get_page_count(Path("a.pdf"))

    def test_split_rejects_non_pdf(self, tmp_path):
        splitter = PDFSplitter(temp_dir=tmp_path)
        with pytest.raises(ValueError):
            splitter.split_pdf(tmp_path / "doc.txt", upload_to_minio=False)


def test_page_budget_rejects_before_extraction_or_minio(tmp_path, monkeypatch):
    from shared.config import get_settings
    from shared.pdf_splitter import PDFPageLimitError
    monkeypatch.setattr(get_settings(), 'max_pdf_pages', 2)
    splitter = PDFSplitter(tmp_path / 'pages')
    monkeypatch.setattr(splitter, 'get_page_count', lambda path: 3)
    with pytest.raises(PDFPageLimitError, match='PDF_PAGE_LIMIT_EXCEEDED'):
        splitter.split_pdf(tmp_path / 'large.pdf')
    assert list(splitter.temp_dir.iterdir()) == []


def test_page_budget_preserves_pdf_at_limit(tmp_path, monkeypatch):
    from shared.config import get_settings
    monkeypatch.setattr(get_settings(), 'max_pdf_pages', 2)
    source = tmp_path / 'small.pdf'
    source.write_bytes(b'%PDF-source')
    splitter = PDFSplitter(tmp_path / 'pages')
    monkeypatch.setattr(splitter, 'get_page_count', lambda path: 2)
    extracted = []
    def extract(arguments, **kwargs):
        extracted.append(arguments)
        Path(arguments[-1]).write_bytes(b'%PDF-page')
    monkeypatch.setattr(subprocess, 'run', extract)
    pages = splitter.split_pdf(source, upload_to_minio=False)
    assert [number for number, _, _ in pages] == [1, 2]
    assert all(path.read_bytes() == b'%PDF-page' for _, path, _ in pages)
    assert source.read_bytes() == b'%PDF-source'
    assert len(extracted) == 2
