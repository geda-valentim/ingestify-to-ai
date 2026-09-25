"""
Tests for MinIO Crawler Storage Adapter
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from infrastructure.adapters.minio_crawler_storage_adapter import MinioCrawlerStorageAdapter
from domain.value_objects.crawler_enums import AssetType


@pytest.fixture
def mock_minio_client():
    """Mock do MinIOClient"""
    client = Mock()
    client.bucket_crawled = "ingestify-crawled"
    client.upload_file = Mock()
    client.upload_content = Mock()
    client.list_objects = Mock(return_value=[])
    client.delete_folder = Mock(return_value=0)
    client.get_presigned_url = Mock(return_value="https://minio.example.com/presigned-url")
    return client


@pytest.fixture
def adapter(mock_minio_client):
    """Fixture para adapter"""
    return MinioCrawlerStorageAdapter(mock_minio_client)


@pytest.fixture
def sample_file(tmp_path):
    """Cria arquivo de teste"""
    file = tmp_path / "test.pdf"
    file.write_bytes(b"PDF content")
    return file


class TestUploadCrawledFile:
    """Testes de upload de arquivo crawleado"""

    @pytest.mark.asyncio
    async def test_upload_crawled_file_success(self, adapter, sample_file, mock_minio_client):
        """Teste: Upload de arquivo bem-sucedido"""
        execution_id = "exec-123"
        source_url = "https://example.com/file.pdf"

        object_name = await adapter.upload_crawled_file(
            execution_id=execution_id,
            file_path=sample_file,
            source_url=source_url,
            content_type="application/pdf"
        )

        # Verificar estrutura do path
        assert object_name == f"crawled/{execution_id}/files/{sample_file.name}"

        # Verificar chamada ao MinIO client
        mock_minio_client.upload_file.assert_called_once()
        call_args = mock_minio_client.upload_file.call_args

        assert call_args[1]["object_name"] == object_name
        assert call_args[1]["content_type"] == "application/pdf"
        assert call_args[1]["metadata"]["source-url"] == source_url
        assert call_args[1]["metadata"]["execution-id"] == execution_id

    @pytest.mark.asyncio
    async def test_upload_crawled_file_without_content_type(self, adapter, sample_file, mock_minio_client):
        """Teste: Upload sem content_type especificado"""
        object_name = await adapter.upload_crawled_file(
            execution_id="exec-123",
            file_path=sample_file,
            source_url="https://example.com/file.pdf"
        )

        mock_minio_client.upload_file.assert_called_once()
        call_args = mock_minio_client.upload_file.call_args
        assert call_args[1]["content_type"] is None


class TestUploadHTMLPage:
    """Testes de upload de página HTML"""

    @pytest.mark.asyncio
    async def test_upload_html_page_success(self, adapter, mock_minio_client):
        """Teste: Upload de página HTML"""
        execution_id = "exec-123"
        url = "https://example.com/page.html"
        html_content = "<html><body>Test</body></html>"

        object_name = await adapter.upload_html_page(
            execution_id=execution_id,
            url=url,
            html_content=html_content
        )

        # Verificar estrutura do path
        assert object_name.startswith(f"crawled/{execution_id}/pages/")
        assert object_name.endswith(".html")

        # Verificar chamada ao MinIO client
        mock_minio_client.upload_content.assert_called_once()
        call_args = mock_minio_client.upload_content.call_args

        assert call_args[1]["content"] == html_content
        assert call_args[1]["content_type"] == "text/html; charset=utf-8"
        assert call_args[1]["metadata"]["source-url"] == url

    @pytest.mark.asyncio
    async def test_upload_html_page_with_page_number(self, adapter, mock_minio_client):
        """Teste: Upload de HTML com número de página"""
        object_name = await adapter.upload_html_page(
            execution_id="exec-123",
            url="https://example.com/page.html",
            html_content="<html></html>",
            page_number=5
        )

        # Deve conter page_5 no nome
        assert "page_5" in object_name

        # Verificar metadata
        call_args = mock_minio_client.upload_content.call_args
        assert call_args[1]["metadata"]["page-number"] == "5"


class TestUploadAsset:
    """Testes de upload de assets"""

    @pytest.mark.asyncio
    async def test_upload_css_asset(self, adapter, sample_file, mock_minio_client):
        """Teste: Upload de CSS asset"""
        execution_id = "exec-123"
        source_url = "https://example.com/style.css"

        object_name = await adapter.upload_asset(
            execution_id=execution_id,
            asset_type=AssetType.CSS,
            file_path=sample_file,
            source_url=source_url,
            content_type="text/css"
        )

        # Verificar estrutura do path
        assert object_name == f"crawled/{execution_id}/assets/css/{sample_file.name}"

        # Verificar metadata
        call_args = mock_minio_client.upload_file.call_args
        assert call_args[1]["metadata"]["asset-type"] == "css"  # AssetType.CSS.value é "css"
        assert call_args[1]["metadata"]["source-url"] == source_url

    @pytest.mark.asyncio
    async def test_upload_image_asset(self, adapter, sample_file, mock_minio_client):
        """Teste: Upload de imagem"""
        object_name = await adapter.upload_asset(
            execution_id="exec-123",
            asset_type=AssetType.IMAGES,
            file_path=sample_file,
            source_url="https://example.com/image.png",
            content_type="image/png"
        )

        # Deve estar em assets/images/
        assert "assets/images/" in object_name

    @pytest.mark.asyncio
    async def test_upload_js_asset(self, adapter, sample_file, mock_minio_client):
        """Teste: Upload de JavaScript"""
        object_name = await adapter.upload_asset(
            execution_id="exec-123",
            asset_type=AssetType.JS,
            file_path=sample_file,
            source_url="https://example.com/app.js",
        )

        # Deve estar em assets/js/
        assert "assets/js/" in object_name


class TestUploadMergedPDF:
    """Testes de upload de PDF merged"""

    @pytest.mark.asyncio
    async def test_upload_merged_pdf_success(self, adapter, sample_file, mock_minio_client):
        """Teste: Upload de PDF merged"""
        execution_id = "exec-123"
        source_urls = [
            "https://example.com/file1.pdf",
            "https://example.com/file2.pdf",
        ]
        total_pages = 20

        object_name = await adapter.upload_merged_pdf(
            execution_id=execution_id,
            file_path=sample_file,
            source_urls=source_urls,
            total_pages=total_pages
        )

        # Verificar estrutura do path
        assert object_name == f"crawled/{execution_id}/merged/{sample_file.name}"

        # Verificar metadata
        call_args = mock_minio_client.upload_file.call_args
        assert call_args[1]["content_type"] == "application/pdf"
        assert call_args[1]["metadata"]["total-pages"] == "20"
        assert call_args[1]["metadata"]["file-type"] == "merged-pdf"
        assert "file1.pdf" in call_args[1]["metadata"]["source-urls"]


class TestListExecutionFiles:
    """Testes de listagem de arquivos"""

    def test_list_execution_files_all(self, adapter, mock_minio_client):
        """Teste: Listar todos os arquivos de uma execução"""
        execution_id = "exec-123"

        mock_objects = [
            Mock(object_name="crawled/exec-123/files/test.pdf", size=1000, last_modified=datetime.now(), etag="abc"),
            Mock(object_name="crawled/exec-123/pages/page.html", size=500, last_modified=datetime.now(), etag="def"),
        ]
        mock_minio_client.list_objects.return_value = mock_objects

        files = adapter.list_execution_files(execution_id)

        assert len(files) == 2
        assert files[0]["object_name"] == "crawled/exec-123/files/test.pdf"
        assert files[0]["size"] == 1000

        # Verificar chamada ao MinIO
        mock_minio_client.list_objects.assert_called_once_with(
            bucket_name="ingestify-crawled",
            prefix=f"crawled/{execution_id}/"
        )

    def test_list_execution_files_by_type(self, adapter, mock_minio_client):
        """Teste: Listar arquivos por tipo"""
        execution_id = "exec-123"
        mock_minio_client.list_objects.return_value = []

        adapter.list_execution_files(execution_id, file_type="files")

        # Verificar que prefix inclui tipo
        call_args = mock_minio_client.list_objects.call_args
        assert call_args[1]["prefix"] == f"crawled/{execution_id}/files/"


class TestDeleteExecutionFolder:
    """Testes de cleanup"""

    @pytest.mark.asyncio
    async def test_delete_execution_folder(self, adapter, mock_minio_client):
        """Teste: Deletar pasta de execução"""
        execution_id = "exec-123"
        mock_minio_client.delete_folder.return_value = 10

        deleted_count = await adapter.delete_execution_folder(execution_id)

        assert deleted_count == 10

        # Verificar chamada ao MinIO
        mock_minio_client.delete_folder.assert_called_once_with(
            bucket_name="ingestify-crawled",
            prefix=f"crawled/{execution_id}/"
        )


class TestGetDownloadURL:
    """Testes de geração de URL pre-signed"""

    def test_get_download_url_default_expiry(self, adapter, mock_minio_client):
        """Teste: Gerar URL com expiry padrão"""
        object_name = "crawled/exec-123/files/test.pdf"

        url = adapter.get_download_url(object_name)

        assert url == "https://minio.example.com/presigned-url"

        # Verificar chamada ao MinIO
        call_args = mock_minio_client.get_presigned_url.call_args
        assert call_args[1]["object_name"] == object_name
        assert call_args[1]["expiry"] == timedelta(hours=24)

    def test_get_download_url_custom_expiry(self, adapter, mock_minio_client):
        """Teste: Gerar URL com expiry customizado"""
        object_name = "crawled/exec-123/files/test.pdf"

        adapter.get_download_url(object_name, expiry_hours=48)

        call_args = mock_minio_client.get_presigned_url.call_args
        assert call_args[1]["expiry"] == timedelta(hours=48)


class TestGetExecutionSummary:
    """Testes de sumário de execução"""

    def test_get_execution_summary(self, adapter, mock_minio_client):
        """Teste: Obter sumário de execução"""
        execution_id = "exec-123"

        mock_objects = [
            Mock(object_name="crawled/exec-123/files/test.pdf", size=1000, last_modified=datetime.now(), etag="abc"),
            Mock(object_name="crawled/exec-123/files/test2.pdf", size=2000, last_modified=datetime.now(), etag="def"),
            Mock(object_name="crawled/exec-123/pages/page.html", size=500, last_modified=datetime.now(), etag="ghi"),
            Mock(object_name="crawled/exec-123/assets/css/style.css", size=300, last_modified=datetime.now(), etag="jkl"),
        ]
        mock_minio_client.list_objects.return_value = mock_objects

        summary = adapter.get_execution_summary(execution_id)

        assert summary["execution_id"] == execution_id
        assert summary["total_files"] == 4
        assert summary["total_size_bytes"] == 3800
        assert summary["file_types"]["files"] == 2
        assert summary["file_types"]["pages"] == 1
        assert summary["file_types"]["assets"] == 1
