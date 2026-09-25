"""
Tests for PyPDF Merger Adapter
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from infrastructure.adapters.pypdf_merger_adapter import PyPDFMergerAdapter
from application.ports.pdf_merger_port import (
    PDFBookmark,
    MergeResult,
    PDFMergerError,
    PDFValidationError,
    PDFCorruptedError,
)


@pytest.fixture
def adapter():
    """Fixture para adapter"""
    return PyPDFMergerAdapter()


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Cria PDF de teste"""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 mock content")
    return pdf_file


@pytest.fixture
def multiple_pdf_paths(tmp_path):
    """Cria múltiplos PDFs de teste"""
    pdfs = []
    for i in range(3):
        pdf_file = tmp_path / f"test_{i}.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 mock content")
        pdfs.append(pdf_file)
    return pdfs


class TestMergePDFs:
    """Testes de merge de PDFs"""

    @pytest.mark.asyncio
    async def test_merge_pdfs_success(self, adapter, multiple_pdf_paths, tmp_path):
        """Teste: Merge de PDFs bem-sucedido"""
        output_path = tmp_path / "merged.pdf"

        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfMerger') as mock_merger_class:
            mock_merger = Mock()
            mock_merger_class.return_value = mock_merger

            with patch.object(adapter, 'validate_pdf', new_callable=AsyncMock, return_value=True):
                with patch.object(adapter, 'get_pdf_info', new_callable=AsyncMock) as mock_info:
                    mock_info.return_value = {"page_count": 10}

                    # Simular criação do arquivo
                    def mock_write(path):
                        Path(path).write_bytes(b"merged pdf content")

                    mock_merger.write.side_effect = mock_write

                    result = await adapter.merge_pdfs(
                        pdf_files=multiple_pdf_paths,
                        output_path=output_path
                    )

                    assert isinstance(result, MergeResult)
                    assert result.success is True
                    assert result.output_path == output_path
                    assert result.source_files_count == 3
                    assert result.total_pages == 10

                    # Verificar chamadas ao merger
                    assert mock_merger.append.call_count == 3
                    mock_merger.write.assert_called_once()
                    mock_merger.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_merge_pdfs_with_bookmarks(self, adapter, multiple_pdf_paths, tmp_path):
        """Teste: Merge com bookmarks"""
        output_path = tmp_path / "merged.pdf"
        bookmarks = [
            PDFBookmark(title="Chapter 1", page_number=0),
            PDFBookmark(title="Chapter 2", page_number=5),
        ]

        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfMerger') as mock_merger_class:
            mock_merger = Mock()
            mock_merger_class.return_value = mock_merger

            with patch.object(adapter, 'validate_pdf', new_callable=AsyncMock, return_value=True):
                with patch.object(adapter, 'get_pdf_info', new_callable=AsyncMock) as mock_info:
                    mock_info.return_value = {"page_count": 10}

                    def mock_write(path):
                        Path(path).write_bytes(b"merged pdf content")

                    mock_merger.write.side_effect = mock_write

                    result = await adapter.merge_pdfs(
                        pdf_files=multiple_pdf_paths,
                        output_path=output_path,
                        bookmarks=bookmarks
                    )

                    assert result.success is True
                    # Verificar que bookmarks foram adicionados
                    assert mock_merger.add_outline_item.call_count == 2

    @pytest.mark.asyncio
    async def test_merge_pdfs_empty_list(self, adapter, tmp_path):
        """Teste: Merge com lista vazia"""
        output_path = tmp_path / "merged.pdf"

        with pytest.raises(PDFMergerError, match="No PDF files provided"):
            await adapter.merge_pdfs(
                pdf_files=[],
                output_path=output_path
            )

    @pytest.mark.asyncio
    async def test_merge_pdfs_file_not_found(self, adapter, tmp_path):
        """Teste: Merge com arquivo inexistente"""
        output_path = tmp_path / "merged.pdf"
        fake_pdf = tmp_path / "nonexistent.pdf"

        with pytest.raises(PDFMergerError, match="PDF file not found"):
            await adapter.merge_pdfs(
                pdf_files=[fake_pdf],
                output_path=output_path
            )

    @pytest.mark.asyncio
    async def test_merge_pdfs_invalid_pdf(self, adapter, multiple_pdf_paths, tmp_path):
        """Teste: Merge com PDF inválido"""
        output_path = tmp_path / "merged.pdf"

        with patch.object(adapter, 'validate_pdf', new_callable=AsyncMock, return_value=False):
            with pytest.raises(PDFValidationError, match="Invalid or corrupted PDF"):
                await adapter.merge_pdfs(
                    pdf_files=multiple_pdf_paths,
                    output_path=output_path
                )


class TestValidatePDF:
    """Testes de validação de PDF"""

    @pytest.mark.asyncio
    async def test_validate_pdf_success(self, adapter, sample_pdf_path):
        """Teste: PDF válido"""
        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfReader') as mock_reader_class:
            mock_reader = Mock()
            mock_reader.pages = [Mock()]  # 1 página
            mock_reader_class.return_value = mock_reader

            result = await adapter.validate_pdf(sample_pdf_path)

            assert result is True

    @pytest.mark.asyncio
    async def test_validate_pdf_file_not_found(self, adapter, tmp_path):
        """Teste: Arquivo não encontrado"""
        fake_file = tmp_path / "nonexistent.pdf"

        result = await adapter.validate_pdf(fake_file)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_pdf_corrupted(self, adapter, sample_pdf_path):
        """Teste: PDF corrompido"""
        from PyPDF2.errors import PdfReadError

        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfReader') as mock_reader_class:
            mock_reader_class.side_effect = PdfReadError("Corrupted")

            result = await adapter.validate_pdf(sample_pdf_path)

            assert result is False

    @pytest.mark.asyncio
    async def test_validate_pdf_no_pages(self, adapter, sample_pdf_path):
        """Teste: PDF sem páginas"""
        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfReader') as mock_reader_class:
            mock_reader = Mock()
            mock_reader.pages = []  # Sem páginas
            mock_reader_class.return_value = mock_reader

            result = await adapter.validate_pdf(sample_pdf_path)

            assert result is False


class TestGetPDFInfo:
    """Testes de extração de informações"""

    @pytest.mark.asyncio
    async def test_get_pdf_info_success(self, adapter, sample_pdf_path):
        """Teste: Extração de informações bem-sucedida"""
        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfReader') as mock_reader_class:
            mock_reader = Mock()
            mock_reader.pages = [Mock(), Mock(), Mock()]  # 3 páginas
            mock_reader.metadata = {
                "/Title": "Test Document",
                "/Author": "Test Author",
                "/Subject": "Test Subject",
                "/Creator": "Test Creator",
                "/Producer": "Test Producer",
                "/CreationDate": "D:20240115120000",
                "/ModDate": "D:20240115130000",
            }
            mock_reader_class.return_value = mock_reader

            info = await adapter.get_pdf_info(sample_pdf_path)

            assert info["page_count"] == 3
            assert info["title"] == "Test Document"
            assert info["author"] == "Test Author"
            assert info["subject"] == "Test Subject"
            assert isinstance(info["created"], datetime)
            assert isinstance(info["modified"], datetime)

    @pytest.mark.asyncio
    async def test_get_pdf_info_file_not_found(self, adapter, tmp_path):
        """Teste: Arquivo não encontrado"""
        fake_file = tmp_path / "nonexistent.pdf"

        with pytest.raises(PDFMergerError, match="PDF file not found"):
            await adapter.get_pdf_info(fake_file)

    @pytest.mark.asyncio
    async def test_get_pdf_info_corrupted(self, adapter, sample_pdf_path):
        """Teste: PDF corrompido"""
        from PyPDF2.errors import PdfReadError

        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfReader') as mock_reader_class:
            mock_reader_class.side_effect = PdfReadError("Corrupted")

            with pytest.raises(PDFCorruptedError, match="Corrupted PDF"):
                await adapter.get_pdf_info(sample_pdf_path)


class TestAddBookmarks:
    """Testes de adição de bookmarks"""

    @pytest.mark.asyncio
    async def test_add_bookmarks_success(self, adapter, sample_pdf_path, tmp_path):
        """Teste: Adição de bookmarks bem-sucedida"""
        output_path = tmp_path / "with_bookmarks.pdf"
        bookmarks = [
            PDFBookmark(title="Section 1", page_number=0),
            PDFBookmark(title="Section 2", page_number=5),
        ]

        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfReader') as mock_reader_class:
            mock_reader = Mock()
            mock_reader.pages = [Mock(), Mock()]
            mock_reader_class.return_value = mock_reader

            with patch('infrastructure.adapters.pypdf_merger_adapter.PdfWriter') as mock_writer_class:
                mock_writer = Mock()
                mock_writer_class.return_value = mock_writer

                with patch('builtins.open', create=True):
                    result = await adapter.add_bookmarks(
                        pdf_file=sample_pdf_path,
                        bookmarks=bookmarks,
                        output_path=output_path
                    )

                    assert result == output_path
                    assert mock_writer.add_outline_item.call_count == 2

    @pytest.mark.asyncio
    async def test_add_bookmarks_file_not_found(self, adapter, tmp_path):
        """Teste: Arquivo não encontrado"""
        fake_file = tmp_path / "nonexistent.pdf"
        bookmarks = [PDFBookmark(title="Test", page_number=0)]

        with pytest.raises(PDFMergerError, match="PDF file not found"):
            await adapter.add_bookmarks(
                pdf_file=fake_file,
                bookmarks=bookmarks
            )


class TestCompressPDF:
    """Testes de compressão de PDF"""

    @pytest.mark.asyncio
    async def test_compress_pdf_success(self, adapter, sample_pdf_path, tmp_path):
        """Teste: Compressão bem-sucedida"""
        output_path = tmp_path / "compressed.pdf"

        with patch('infrastructure.adapters.pypdf_merger_adapter.PdfReader') as mock_reader_class:
            mock_reader = Mock()
            mock_page = Mock()
            mock_page.compress_content_streams = Mock()
            mock_reader.pages = [mock_page]
            mock_reader_class.return_value = mock_reader

            with patch('infrastructure.adapters.pypdf_merger_adapter.PdfWriter') as mock_writer_class:
                mock_writer = Mock()
                mock_writer_class.return_value = mock_writer

                with patch('builtins.open', create=True):
                    # Simular criação do arquivo
                    output_path.write_bytes(b"compressed content")

                    result = await adapter.compress_pdf(
                        pdf_file=sample_pdf_path,
                        output_path=output_path
                    )

                    assert result == output_path
                    mock_page.compress_content_streams.assert_called_once()
                    mock_writer.add_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_compress_pdf_file_not_found(self, adapter, tmp_path):
        """Teste: Arquivo não encontrado"""
        fake_file = tmp_path / "nonexistent.pdf"

        with pytest.raises(PDFMergerError, match="PDF file not found"):
            await adapter.compress_pdf(fake_file)


class TestParsePDFDate:
    """Testes de parsing de data PDF"""

    def test_parse_pdf_date_success(self, adapter):
        """Teste: Parse de data bem-sucedido"""
        date_str = "D:20240115120000"

        result = adapter._parse_pdf_date(date_str)

        assert result == datetime(2024, 1, 15, 12, 0, 0)

    def test_parse_pdf_date_with_timezone(self, adapter):
        """Teste: Parse de data com timezone"""
        date_str = "D:20240115120000+00'00'"

        result = adapter._parse_pdf_date(date_str)

        assert result == datetime(2024, 1, 15, 12, 0, 0)

    def test_parse_pdf_date_invalid(self, adapter):
        """Teste: Parse de data inválida"""
        date_str = "invalid_date"

        result = adapter._parse_pdf_date(date_str)

        assert result is None

    def test_parse_pdf_date_no_d_prefix(self, adapter):
        """Teste: Parse de data sem prefixo D:"""
        date_str = "20240115120000"

        result = adapter._parse_pdf_date(date_str)

        assert result is None
