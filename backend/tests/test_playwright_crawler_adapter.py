"""
Tests for Playwright Crawler Adapter
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from infrastructure.adapters.playwright_crawler_adapter import PlaywrightCrawlerAdapter
from application.ports.crawler_port import (
    CrawlResult,
    DownloadResult,
    CrawlerError,
    CrawlerTimeoutError,
)
from domain.value_objects.crawler_enums import AssetType
from domain.value_objects.proxy_config import ProxyConfig


@pytest.fixture
def crawler():
    """Fixture para crawler sem proxy"""
    return PlaywrightCrawlerAdapter(
        headless=True,
        browser_type="chromium",
        timeout_seconds=10,
    )


@pytest.fixture
def crawler_with_proxy():
    """Fixture para crawler com proxy"""
    proxy = ProxyConfig(
        host="proxy.example.com",
        port=8080,
        protocol="http",
        username="user",
        password="pass",
    )
    return PlaywrightCrawlerAdapter(
        proxy_config=proxy,
        headless=True,
    )


@pytest.fixture
def mock_playwright_page():
    """Mock de Playwright Page"""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.content = AsyncMock(return_value="<html><body><a href='/test.pdf'>Link</a></body></html>")
    page.evaluate = AsyncMock(return_value=["/test.pdf"])
    page.wait_for_load_state = AsyncMock()
    page.close = AsyncMock()
    return page


class TestInitialization:
    """Testes de inicialização"""

    def test_init_without_proxy(self):
        """Teste: Inicialização sem proxy"""
        crawler = PlaywrightCrawlerAdapter(
            headless=True,
            browser_type="chromium",
            timeout_seconds=15,
        )

        assert crawler.headless is True
        assert crawler.browser_type_name == "chromium"
        assert crawler.timeout_ms == 15000
        assert crawler.proxy_config is None
        assert crawler.browser is None  # Lazy init

    def test_init_with_proxy(self):
        """Teste: Inicialização com proxy"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
            username="user",
            password="pass",
        )

        crawler = PlaywrightCrawlerAdapter(proxy_config=proxy)

        assert crawler.proxy_config is not None
        assert crawler.proxy_config["server"] == "http://user:pass@proxy.example.com:8080"
        assert crawler.proxy_config["username"] == "user"
        assert crawler.proxy_config["password"] == "pass"

    def test_init_firefox_browser(self):
        """Teste: Inicialização com Firefox"""
        crawler = PlaywrightCrawlerAdapter(browser_type="firefox")
        assert crawler.browser_type_name == "firefox"

    def test_init_webkit_browser(self):
        """Teste: Inicialização com WebKit"""
        crawler = PlaywrightCrawlerAdapter(browser_type="webkit")
        assert crawler.browser_type_name == "webkit"


class TestBrowserLaunch:
    """Testes de inicialização do browser"""

    @pytest.mark.asyncio
    async def test_ensure_browser_launched_chromium(self, crawler):
        """Teste: Lazy init do browser Chromium"""
        with patch('infrastructure.adapters.playwright_crawler_adapter.async_playwright') as mock_playwright:
            mock_pw_instance = AsyncMock()
            mock_playwright.return_value.start = AsyncMock(return_value=mock_pw_instance)

            mock_browser = AsyncMock()
            mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)

            mock_context = AsyncMock()
            mock_browser.new_context = AsyncMock(return_value=mock_context)

            await crawler._ensure_browser_launched()

            assert crawler.browser is not None
            assert crawler.context is not None
            mock_pw_instance.chromium.launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_browser_launched_only_once(self, crawler):
        """Teste: Browser só é inicializado uma vez"""
        with patch('infrastructure.adapters.playwright_crawler_adapter.async_playwright') as mock_playwright:
            mock_pw_instance = AsyncMock()
            mock_playwright.return_value.start = AsyncMock(return_value=mock_pw_instance)

            mock_browser = AsyncMock()
            mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=AsyncMock())

            # Chamar duas vezes
            await crawler._ensure_browser_launched()
            await crawler._ensure_browser_launched()

            # Deve lançar apenas uma vez
            assert mock_pw_instance.chromium.launch.call_count == 1


class TestCrawlPage:
    """Testes de crawl de página"""

    @pytest.mark.asyncio
    async def test_crawl_page_success(self, crawler, mock_playwright_page):
        """Teste: Crawl de página bem-sucedido"""
        with patch.object(crawler, '_ensure_browser_launched', new_callable=AsyncMock):
            mock_response = Mock()
            mock_response.status = 200
            mock_playwright_page.goto.return_value = mock_response

            crawler.context = AsyncMock()
            crawler.context.new_page = AsyncMock(return_value=mock_playwright_page)

            result = await crawler.crawl_page("https://example.com")

            assert isinstance(result, CrawlResult)
            assert result.url == "https://example.com"
            assert result.status_code == 200
            assert len(result.links) > 0

    @pytest.mark.asyncio
    async def test_crawl_page_with_extension_filter(self, crawler, mock_playwright_page):
        """Teste: Crawl com filtro por extensão"""
        with patch.object(crawler, '_ensure_browser_launched', new_callable=AsyncMock):
            mock_response = Mock()
            mock_response.status = 200
            mock_playwright_page.goto.return_value = mock_response
            mock_playwright_page.evaluate.return_value = [
                "https://example.com/page.html",
                "https://example.com/doc.pdf",
                "https://example.com/file.pdf",
            ]

            crawler.context = AsyncMock()
            crawler.context.new_page = AsyncMock(return_value=mock_playwright_page)

            result = await crawler.crawl_page(
                "https://example.com",
                file_extensions=["pdf"]
            )

            # Apenas PDFs
            assert len(result.links) == 2
            assert all(link.endswith(".pdf") for link in result.links)

    @pytest.mark.asyncio
    async def test_crawl_page_timeout(self, crawler):
        """Teste: Timeout ao crawlear página"""
        import asyncio

        with patch.object(crawler, '_ensure_browser_launched', new_callable=AsyncMock):
            mock_page = AsyncMock()
            mock_page.goto.side_effect = asyncio.TimeoutError("Timeout")
            mock_page.close = AsyncMock()

            crawler.context = AsyncMock()
            crawler.context.new_page = AsyncMock(return_value=mock_page)

            with pytest.raises(CrawlerTimeoutError):
                await crawler.crawl_page("https://example.com")

            # Página deve ser fechada mesmo com erro
            mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_crawl_page_no_response(self, crawler):
        """Teste: Navegação retorna None"""
        with patch.object(crawler, '_ensure_browser_launched', new_callable=AsyncMock):
            mock_page = AsyncMock()
            mock_page.goto.return_value = None  # Falha na navegação
            mock_page.close = AsyncMock()

            crawler.context = AsyncMock()
            crawler.context.new_page = AsyncMock(return_value=mock_page)

            with pytest.raises(CrawlerError, match="Failed to navigate"):
                await crawler.crawl_page("https://example.com")


class TestDownloadFile:
    """Testes de download de arquivo"""

    @pytest.mark.asyncio
    async def test_download_file_success(self, crawler, tmp_path):
        """Teste: Download de arquivo bem-sucedido"""
        destination = tmp_path / "test.pdf"
        file_content = b"PDF content"

        with patch.object(crawler, '_ensure_browser_launched', new_callable=AsyncMock):
            mock_response = Mock()
            mock_response.headers = {"content-type": "application/pdf"}
            mock_response.body = AsyncMock(return_value=file_content)

            mock_page = AsyncMock()
            mock_page.goto.return_value = mock_response
            mock_page.close = AsyncMock()

            crawler.context = AsyncMock()
            crawler.context.new_page = AsyncMock(return_value=mock_page)

            result = await crawler.download_file(
                "https://example.com/file.pdf",
                destination
            )

            assert result.success is True
            assert result.file_path == destination
            assert result.file_size_bytes == len(file_content)
            assert destination.exists()

    @pytest.mark.asyncio
    async def test_download_file_timeout(self, crawler, tmp_path):
        """Teste: Timeout ao baixar arquivo"""
        import asyncio

        destination = tmp_path / "test.pdf"

        with patch.object(crawler, '_ensure_browser_launched', new_callable=AsyncMock):
            mock_page = AsyncMock()
            mock_page.goto.side_effect = asyncio.TimeoutError("Timeout")
            mock_page.close = AsyncMock()

            crawler.context = AsyncMock()
            crawler.context.new_page = AsyncMock(return_value=mock_page)

            result = await crawler.download_file(
                "https://example.com/file.pdf",
                destination
            )

            assert result.success is False
            assert "Timeout" in result.error


class TestExtractAssets:
    """Testes de extração de assets"""

    @pytest.mark.asyncio
    async def test_extract_assets_css_and_js(self, crawler):
        """Teste: Extração de CSS e JS via network interception"""
        with patch.object(crawler, '_ensure_browser_launched', new_callable=AsyncMock):
            mock_page = AsyncMock()

            # Simular requests capturados
            captured_requests = []

            def mock_on(event, handler):
                if event == "request":
                    # Simular alguns requests
                    mock_req1 = Mock()
                    mock_req1.resource_type = "stylesheet"
                    mock_req1.url = "https://example.com/style.css"

                    mock_req2 = Mock()
                    mock_req2.resource_type = "script"
                    mock_req2.url = "https://example.com/app.js"

                    handler(mock_req1)
                    handler(mock_req2)

            mock_page.on = mock_on
            mock_page.goto = AsyncMock()
            mock_page.wait_for_load_state = AsyncMock()
            mock_page.close = AsyncMock()

            crawler.context = AsyncMock()
            crawler.context.new_page = AsyncMock(return_value=mock_page)

            assets = await crawler.extract_assets(
                "https://example.com",
                [AssetType.CSS, AssetType.JS]
            )

            assert len(assets[AssetType.CSS]) == 1
            assert len(assets[AssetType.JS]) == 1

    @pytest.mark.asyncio
    async def test_extract_assets_images(self, crawler):
        """Teste: Extração de imagens"""
        with patch.object(crawler, '_ensure_browser_launched', new_callable=AsyncMock):
            mock_page = AsyncMock()

            def mock_on(event, handler):
                if event == "request":
                    mock_req = Mock()
                    mock_req.resource_type = "image"
                    mock_req.url = "https://example.com/image.png"
                    handler(mock_req)

            mock_page.on = mock_on
            mock_page.goto = AsyncMock()
            mock_page.wait_for_load_state = AsyncMock()
            mock_page.close = AsyncMock()

            crawler.context = AsyncMock()
            crawler.context.new_page = AsyncMock(return_value=mock_page)

            assets = await crawler.extract_assets(
                "https://example.com",
                [AssetType.IMAGES]
            )

            assert len(assets[AssetType.IMAGES]) == 1


class TestCleanup:
    """Testes de cleanup"""

    @pytest.mark.asyncio
    async def test_close_browser(self, crawler):
        """Teste: Fechar browser e liberar recursos"""
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        mock_context.close = AsyncMock()
        mock_browser.close = AsyncMock()
        mock_playwright.stop = AsyncMock()

        crawler.context = mock_context
        crawler.browser = mock_browser
        crawler.playwright = mock_playwright

        await crawler.close()

        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

        assert crawler.context is None
        assert crawler.browser is None
        assert crawler.playwright is None

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self, crawler):
        """Teste: Fechar quando browser não foi inicializado"""
        # Não deve dar erro
        await crawler.close()

        assert crawler.browser is None
        assert crawler.context is None
