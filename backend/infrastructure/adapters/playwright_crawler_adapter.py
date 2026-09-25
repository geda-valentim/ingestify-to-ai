"""
Playwright Crawler Adapter

Implementação de crawler usando Playwright para sites com JavaScript
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from application.ports.crawler_port import (
    CrawlerPort,
    CrawlResult,
    DownloadResult,
    CrawlerError,
    CrawlerTimeoutError,
    CrawlerConnectionError,
)
from domain.value_objects.crawler_enums import AssetType
from domain.value_objects.proxy_config import ProxyConfig
from shared.config import get_settings

logger = logging.getLogger(__name__)


class PlaywrightCrawlerAdapter(CrawlerPort):
    """
    Crawler adapter usando Playwright para sites com JavaScript

    Características:
    - Browser automation (Chromium/Firefox/WebKit)
    - JavaScript rendering completo
    - Network request interception
    - Captura de assets carregados dinamicamente
    - Suporte a proxy
    - Headless mode configurável
    """

    def __init__(
        self,
        proxy_config: Optional[ProxyConfig] = None,
        headless: Optional[bool] = None,
        browser_type: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        """
        Inicializa Playwright crawler

        Args:
            proxy_config: Configuração de proxy (opcional)
            headless: Executar browser em modo headless
            browser_type: Tipo de browser (chromium, firefox, webkit)
            timeout_seconds: Timeout para operações
        """
        settings = get_settings()

        self.headless = headless if headless is not None else settings.playwright_headless
        self.browser_type_name = browser_type or settings.playwright_browser_type
        self.timeout_ms = (timeout_seconds or settings.playwright_timeout_seconds) * 1000

        # Configurar proxy para Playwright
        self.proxy_config = None
        if proxy_config:
            self.proxy_config = {
                "server": proxy_config.url,
            }
            if proxy_config.username and proxy_config.password:
                self.proxy_config["username"] = proxy_config.username
                self.proxy_config["password"] = proxy_config.password

        # Browser não inicializado ainda (lazy init)
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    async def _ensure_browser_launched(self):
        """Inicializa browser se ainda não foi iniciado"""
        if self.browser is not None:
            return

        self.playwright = await async_playwright().start()

        # Selecionar tipo de browser
        if self.browser_type_name == "firefox":
            browser_launcher = self.playwright.firefox
        elif self.browser_type_name == "webkit":
            browser_launcher = self.playwright.webkit
        else:  # chromium (padrão)
            browser_launcher = self.playwright.chromium

        # Lançar browser
        self.browser = await browser_launcher.launch(
            headless=self.headless,
            proxy=self.proxy_config,
        )

        # Criar contexto persistente
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=get_settings().crawler_user_agent,
        )

        logger.info(f"Playwright browser launched: {self.browser_type_name} (headless={self.headless})")

    async def crawl_page(
        self,
        url: str,
        file_extensions: Optional[List[str]] = None
    ) -> CrawlResult:
        """
        Crawl página com Playwright (renderiza JavaScript)

        Args:
            url: URL da página
            file_extensions: Filtrar links por extensão

        Returns:
            CrawlResult com links encontrados
        """
        await self._ensure_browser_launched()

        page: Optional[Page] = None
        try:
            page = await self.context.new_page()
            page.set_default_timeout(self.timeout_ms)

            # Navegar para URL
            response = await page.goto(url, wait_until='networkidle')

            if not response:
                raise CrawlerError(f"Failed to navigate to {url}")

            # Aguardar renderização completa
            await page.wait_for_load_state('networkidle')

            # Extrair HTML após renderização
            html_content = await page.content()

            # Extrair todos os links usando JavaScript
            links_raw = await page.evaluate('''
                () => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(href => href && !href.startsWith('javascript:') && !href.startsWith('#'));
                }
            ''')

            # Filtrar por extensão se especificado
            if file_extensions:
                links = [
                    link for link in links_raw
                    if any(link.lower().endswith(f".{ext}") for ext in file_extensions)
                ]
            else:
                links = links_raw

            # Remover duplicatas
            links = list(dict.fromkeys(links))

            return CrawlResult(
                url=url,
                links=links,
                html_content=html_content,
                status_code=response.status,
            )

        except asyncio.TimeoutError as e:
            logger.error(f"Timeout crawling {url}")
            raise CrawlerTimeoutError(f"Timeout: {url}") from e

        except Exception as e:
            logger.error(f"Error crawling {url}: {e}", exc_info=True)
            raise CrawlerError(f"Failed to crawl {url}: {e}") from e

        finally:
            if page:
                await page.close()

    async def download_file(
        self,
        url: str,
        destination: Path,
        timeout_seconds: Optional[int] = None
    ) -> DownloadResult:
        """
        Download arquivo usando Playwright

        Args:
            url: URL do arquivo
            destination: Caminho de destino
            timeout_seconds: Timeout customizado

        Returns:
            DownloadResult
        """
        await self._ensure_browser_launched()

        page: Optional[Page] = None
        try:
            # Garantir que o diretório existe
            destination.parent.mkdir(parents=True, exist_ok=True)

            page = await self.context.new_page()

            if timeout_seconds:
                page.set_default_timeout(timeout_seconds * 1000)

            # Navegar diretamente para o arquivo (trigger download)
            response = await page.goto(url)

            if not response:
                raise CrawlerError(f"Failed to download {url}")

            # Salvar conteúdo
            content = await response.body()
            destination.write_bytes(content)

            file_size = len(content)
            content_type = response.headers.get('content-type')

            return DownloadResult(
                url=url,
                file_path=destination,
                file_size_bytes=file_size,
                content_type=content_type,
                success=True,
            )

        except asyncio.TimeoutError as e:
            logger.error(f"Timeout downloading {url}")
            return DownloadResult(
                url=url,
                file_path=destination,
                file_size_bytes=0,
                success=False,
                error=f"Timeout: {e}",
            )

        except Exception as e:
            logger.error(f"Error downloading {url}: {e}", exc_info=True)
            return DownloadResult(
                url=url,
                file_path=destination,
                file_size_bytes=0,
                success=False,
                error=str(e),
            )

        finally:
            if page:
                await page.close()

    async def extract_assets(
        self,
        url: str,
        asset_types: List[AssetType]
    ) -> Dict[AssetType, List[str]]:
        """
        Extrai assets usando Playwright (captura network requests)

        Args:
            url: URL da página
            asset_types: Tipos de assets para extrair

        Returns:
            Dict com assets por tipo
        """
        await self._ensure_browser_launched()

        page: Optional[Page] = None
        try:
            page = await self.context.new_page()

            # Capturar network requests
            captured_assets: Dict[AssetType, List[str]] = {
                asset_type: [] for asset_type in asset_types
            }

            def handle_request(request):
                resource_type = request.resource_type
                req_url = request.url

                # Mapear resource_type do Playwright para AssetType
                if resource_type == "stylesheet" and AssetType.CSS in asset_types:
                    captured_assets[AssetType.CSS].append(req_url)
                elif resource_type == "script" and AssetType.JS in asset_types:
                    captured_assets[AssetType.JS].append(req_url)
                elif resource_type == "image" and AssetType.IMAGES in asset_types:
                    captured_assets[AssetType.IMAGES].append(req_url)
                elif resource_type == "font" and AssetType.FONTS in asset_types:
                    captured_assets[AssetType.FONTS].append(req_url)
                elif resource_type == "media" and AssetType.VIDEOS in asset_types:
                    captured_assets[AssetType.VIDEOS].append(req_url)

            page.on("request", handle_request)

            # Navegar para página (captura assets durante load)
            await page.goto(url, wait_until='networkidle')

            # Aguardar carregamento completo
            await page.wait_for_load_state('networkidle')

            # Remover duplicatas
            for asset_type in captured_assets:
                captured_assets[asset_type] = list(dict.fromkeys(captured_assets[asset_type]))

            return captured_assets

        except Exception as e:
            logger.error(f"Error extracting assets from {url}: {e}", exc_info=True)
            raise CrawlerError(f"Failed to extract assets: {e}") from e

        finally:
            if page:
                await page.close()

    async def download_assets(
        self,
        asset_urls: Dict[AssetType, List[str]],
        destination_folder: Path,
        max_concurrent: int = 10
    ) -> Dict[str, DownloadResult]:
        """
        Download assets em paralelo

        Args:
            asset_urls: Dict com AssetType -> URLs
            destination_folder: Pasta de destino
            max_concurrent: Máximo de downloads simultâneos

        Returns:
            Dict com resultados
        """
        results: Dict[str, DownloadResult] = {}

        # Criar tarefas
        tasks = []
        for asset_type, urls in asset_urls.items():
            type_folder = destination_folder / asset_type.value.lower()
            type_folder.mkdir(parents=True, exist_ok=True)

            for url in urls:
                filename = Path(urlparse(url).path).name or "asset"
                file_path = type_folder / filename
                tasks.append(self._download_asset(url, file_path, results))

        # Limitar concorrência
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_download(task):
            async with semaphore:
                return await task

        await asyncio.gather(*[bounded_download(task) for task in tasks])

        return results

    async def _download_asset(
        self,
        url: str,
        destination: Path,
        results: Dict[str, DownloadResult]
    ):
        """Helper para download com registro"""
        result = await self.download_file(url, destination)
        results[url] = result

    async def close(self):
        """Fecha browser e libera recursos"""
        if self.context:
            await self.context.close()
            self.context = None

        if self.browser:
            await self.browser.close()
            self.browser = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

        logger.info("Playwright browser closed")
