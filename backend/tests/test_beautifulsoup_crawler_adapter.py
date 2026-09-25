"""
Tests for BeautifulSoup Crawler Adapter
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import httpx

from infrastructure.adapters.beautifulsoup_crawler_adapter import BeautifulSoupCrawlerAdapter
from application.ports.crawler_port import (
    CrawlResult,
    DownloadResult,
    CrawlerError,
    CrawlerTimeoutError,
    CrawlerConnectionError,
)
from domain.value_objects.crawler_enums import AssetType
from domain.value_objects.proxy_config import ProxyConfig


@pytest.fixture
def crawler():
    """Fixture para crawler sem proxy"""
    return BeautifulSoupCrawlerAdapter(
        user_agent="TestBot/1.0",
        timeout_seconds=10,
        rate_limit_per_second=5,
    )


@pytest.fixture
def crawler_with_proxy():
    """Fixture para crawler com proxy"""
    proxy = ProxyConfig(
        host="proxy.example.com",
        port=8080,
        protocol="http",
    )
    return BeautifulSoupCrawlerAdapter(
        proxy_config=proxy,
        timeout_seconds=10,
    )


@pytest.fixture
def sample_html():
    """HTML de teste"""
    return """
    <html>
        <head>
            <link rel="stylesheet" href="/style.css">
            <script src="/app.js"></script>
        </head>
        <body>
            <a href="/page1.html">Page 1</a>
            <a href="/document.pdf">PDF</a>
            <a href="https://example.com/external.pdf">External PDF</a>
            <img src="/image.png">
            <img srcset="/image-1x.png 1x, /image-2x.png 2x">
        </body>
    </html>
    """


class TestInitialization:
    """Testes de inicialização"""

    def test_init_without_proxy(self):
        """Teste: Inicialização sem proxy"""
        crawler = BeautifulSoupCrawlerAdapter(
            user_agent="TestBot/1.0",
            timeout_seconds=15,
            rate_limit_per_second=3,
        )

        assert crawler.user_agent == "TestBot/1.0"
        assert crawler.timeout_seconds == 15
        assert crawler.rate_limit == 3
        assert crawler.client is not None

    def test_init_with_proxy(self):
        """Teste: Inicialização com proxy"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
            username="user",
            password="pass",
        )

        crawler = BeautifulSoupCrawlerAdapter(proxy_config=proxy)

        assert crawler.client is not None
        # Proxy está configurado internamente no httpx.AsyncClient


class TestCrawlPage:
    """Testes de crawl de página"""

    @pytest.mark.asyncio
    async def test_crawl_page_success(self, crawler, sample_html):
        """Teste: Crawl de página bem-sucedido"""
        with patch.object(crawler, '_fetch_with_retry', new_callable=AsyncMock) as mock_fetch:
            mock_response = Mock()
            mock_response.text = sample_html
            mock_response.status_code = 200
            mock_fetch.return_value = mock_response

            result = await crawler.crawl_page("https://example.com")

            assert isinstance(result, CrawlResult)
            assert result.url == "https://example.com"
            assert result.status_code == 200
            assert len(result.links) == 3  # 3 links no HTML
            assert "https://example.com/page1.html" in result.links
            assert result.html_content == sample_html

    @pytest.mark.asyncio
    async def test_crawl_page_with_extension_filter(self, crawler, sample_html):
        """Teste: Crawl com filtro por extensão"""
        with patch.object(crawler, '_fetch_with_retry', new_callable=AsyncMock) as mock_fetch:
            mock_response = Mock()
            mock_response.text = sample_html
            mock_response.status_code = 200
            mock_fetch.return_value = mock_response

            result = await crawler.crawl_page(
                "https://example.com",
                file_extensions=["pdf"]
            )

            # Apenas PDFs devem ser retornados
            assert len(result.links) == 2
            assert all(link.endswith(".pdf") for link in result.links)

    @pytest.mark.asyncio
    async def test_crawl_page_timeout(self, crawler):
        """Teste: Timeout ao crawlear página"""
        with patch.object(crawler, '_fetch_with_retry', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = CrawlerTimeoutError("Timeout")

            with pytest.raises(CrawlerTimeoutError):
                await crawler.crawl_page("https://example.com")

    @pytest.mark.asyncio
    async def test_crawl_page_connection_error(self, crawler):
        """Teste: Erro de conexão"""
        with patch.object(crawler, '_fetch_with_retry', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = CrawlerConnectionError("Connection failed")

            with pytest.raises(CrawlerConnectionError):
                await crawler.crawl_page("https://example.com")


class TestDownloadFile:
    """Testes de download de arquivo"""

    @pytest.mark.asyncio
    async def test_download_file_success(self, crawler, tmp_path):
        """Teste: Download de arquivo bem-sucedido"""
        destination = tmp_path / "test.pdf"
        file_content = b"PDF content here"

        with patch.object(crawler.client, 'stream') as mock_stream:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'application/pdf'}
            mock_response.raise_for_status = Mock()

            async def mock_aiter_bytes(chunk_size):
                yield file_content

            mock_response.aiter_bytes = mock_aiter_bytes
            mock_stream.return_value.__aenter__.return_value = mock_response

            with patch.object(crawler, '_apply_rate_limit', new_callable=AsyncMock):
                result = await crawler.download_file(
                    "https://example.com/file.pdf",
                    destination
                )

            assert result.success is True
            assert result.file_path == destination
            assert result.file_size_bytes == len(file_content)
            assert result.content_type == 'application/pdf'
            assert destination.exists()

    @pytest.mark.asyncio
    async def test_download_file_timeout(self, crawler, tmp_path):
        """Teste: Timeout ao baixar arquivo"""
        destination = tmp_path / "test.pdf"

        with patch.object(crawler.client, 'stream') as mock_stream:
            mock_stream.side_effect = httpx.TimeoutException("Timeout")

            with patch.object(crawler, '_apply_rate_limit', new_callable=AsyncMock):
                result = await crawler.download_file(
                    "https://example.com/file.pdf",
                    destination
                )

            assert result.success is False
            assert "Timeout" in result.error


class TestExtractAssets:
    """Testes de extração de assets"""

    @pytest.mark.asyncio
    async def test_extract_css_and_js(self, crawler, sample_html):
        """Teste: Extração de CSS e JS"""
        with patch.object(crawler, '_fetch_with_retry', new_callable=AsyncMock) as mock_fetch:
            mock_response = Mock()
            mock_response.text = sample_html
            mock_fetch.return_value = mock_response

            assets = await crawler.extract_assets(
                "https://example.com",
                [AssetType.CSS, AssetType.JS]
            )

            assert AssetType.CSS in assets
            assert AssetType.JS in assets
            assert len(assets[AssetType.CSS]) == 1
            assert len(assets[AssetType.JS]) == 1
            assert "https://example.com/style.css" in assets[AssetType.CSS]
            assert "https://example.com/app.js" in assets[AssetType.JS]

    @pytest.mark.asyncio
    async def test_extract_images(self, crawler, sample_html):
        """Teste: Extração de imagens (incluindo srcset)"""
        with patch.object(crawler, '_fetch_with_retry', new_callable=AsyncMock) as mock_fetch:
            mock_response = Mock()
            mock_response.text = sample_html
            mock_fetch.return_value = mock_response

            assets = await crawler.extract_assets(
                "https://example.com",
                [AssetType.IMAGES]
            )

            # 1 img com src + 2 do srcset = 3 imagens
            assert len(assets[AssetType.IMAGES]) == 3


class TestRateLimiting:
    """Testes de rate limiting"""

    @pytest.mark.asyncio
    async def test_rate_limit_same_domain(self, crawler):
        """Teste: Rate limit para mesmo domínio"""
        import time

        url = "https://example.com/page1"

        # Primeira request - sem delay
        start = time.time()
        await crawler._apply_rate_limit(url)
        elapsed1 = time.time() - start
        assert elapsed1 < 0.01  # Sem delay significativo

        # Segunda request - deve aplicar delay
        start = time.time()
        await crawler._apply_rate_limit(url)
        elapsed2 = time.time() - start

        # Rate limit é 5 req/s = 0.2s entre requests
        expected_delay = 1.0 / crawler.rate_limit
        assert elapsed2 >= expected_delay * 0.9  # Margem de erro

    @pytest.mark.asyncio
    async def test_rate_limit_different_domains(self, crawler):
        """Teste: Rate limit para domínios diferentes (sem delay)"""
        import time

        url1 = "https://example.com/page1"
        url2 = "https://other.com/page1"

        await crawler._apply_rate_limit(url1)

        # Request para outro domínio não deve aplicar delay
        start = time.time()
        await crawler._apply_rate_limit(url2)
        elapsed = time.time() - start

        assert elapsed < 0.01  # Sem delay significativo


class TestRetryMechanism:
    """Testes de retry automático"""

    @pytest.mark.asyncio
    async def test_fetch_with_retry_success_first_attempt(self, crawler):
        """Teste: Sucesso na primeira tentativa"""
        with patch.object(crawler.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            with patch.object(crawler, '_apply_rate_limit', new_callable=AsyncMock):
                result = await crawler._fetch_with_retry("https://example.com")

            assert result.status_code == 200
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_with_retry_timeout_exhaust_retries(self, crawler):
        """Teste: Timeout em todas as tentativas"""
        with patch.object(crawler.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Timeout")

            with patch.object(crawler, '_apply_rate_limit', new_callable=AsyncMock):
                with pytest.raises(CrawlerTimeoutError):
                    await crawler._fetch_with_retry("https://example.com")

            # Deve tentar max_retries vezes (padrão: 3)
            assert mock_get.call_count == crawler.max_retries


class TestCleanup:
    """Testes de cleanup"""

    @pytest.mark.asyncio
    async def test_close_client(self, crawler):
        """Teste: Fechar httpx client"""
        with patch.object(crawler.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await crawler.close()
            mock_close.assert_called_once()
