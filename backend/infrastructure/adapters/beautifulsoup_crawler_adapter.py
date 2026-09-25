"""
BeautifulSoup Crawler Adapter

Implementação de crawler usando httpx + BeautifulSoup para sites simples (sem JS)
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup

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


class BeautifulSoupCrawlerAdapter(CrawlerPort):
    """
    Crawler adapter usando httpx + BeautifulSoup

    Características:
    - HTTP assíncrono (httpx.AsyncClient)
    - Parsing HTML com BeautifulSoup + lxml
    - Rate limiting por domínio
    - Retry automático (3 tentativas)
    - Suporte a proxy (HTTP/HTTPS/SOCKS5)
    - Download paralelo de assets
    """

    def __init__(
        self,
        proxy_config: Optional[ProxyConfig] = None,
        user_agent: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        rate_limit_per_second: Optional[int] = None,
    ):
        """
        Inicializa crawler adapter

        Args:
            proxy_config: Configuração de proxy (opcional)
            user_agent: User-Agent customizado (opcional)
            timeout_seconds: Timeout padrão para requests
            rate_limit_per_second: Rate limit por domínio
        """
        settings = get_settings()

        self.user_agent = user_agent or settings.crawler_user_agent
        self.timeout_seconds = timeout_seconds or settings.crawler_download_timeout_seconds
        self.rate_limit = rate_limit_per_second or settings.crawler_rate_limit_per_second
        self.max_retries = settings.crawler_max_retries

        # Configurar proxy se fornecido
        proxy = None
        if proxy_config:
            proxy = proxy_config.url

        # Criar httpx client assíncrono
        self.client = httpx.AsyncClient(
            proxy=proxy,
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )

        # Rate limiting: última request por domínio
        self._last_request_time: Dict[str, float] = {}

    async def _apply_rate_limit(self, url: str):
        """Aplica rate limiting por domínio"""
        import time

        domain = urlparse(url).netloc

        if domain in self._last_request_time:
            elapsed = time.time() - self._last_request_time[domain]
            delay = (1.0 / self.rate_limit) - elapsed

            if delay > 0:
                await asyncio.sleep(delay)

        self._last_request_time[domain] = time.time()

    async def _fetch_with_retry(
        self,
        url: str,
        timeout: Optional[int] = None
    ) -> httpx.Response:
        """
        Faz HTTP GET com retry automático

        Args:
            url: URL para fetch
            timeout: Timeout customizado (opcional)

        Returns:
            httpx.Response

        Raises:
            CrawlerError: Se todas as tentativas falharem
        """
        await self._apply_rate_limit(url)

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.get(
                    url,
                    timeout=timeout or self.timeout_seconds
                )
                response.raise_for_status()
                return response

            except httpx.TimeoutException as e:
                logger.warning(f"Timeout fetching {url} (attempt {attempt}/{self.max_retries})")
                if attempt == self.max_retries:
                    raise CrawlerTimeoutError(f"Timeout after {self.max_retries} attempts: {url}") from e

            except httpx.ConnectError as e:
                logger.warning(f"Connection error fetching {url} (attempt {attempt}/{self.max_retries})")
                if attempt == self.max_retries:
                    raise CrawlerConnectionError(f"Connection failed after {self.max_retries} attempts: {url}") from e

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} for {url}")
                raise CrawlerError(f"HTTP {e.response.status_code}: {url}") from e

            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {e}")
                if attempt == self.max_retries:
                    raise CrawlerError(f"Failed to fetch {url}: {e}") from e

            # Exponential backoff
            await asyncio.sleep(2 ** attempt)

    async def crawl_page(
        self,
        url: str,
        file_extensions: Optional[List[str]] = None
    ) -> CrawlResult:
        """
        Crawl página e extrai links

        Args:
            url: URL da página
            file_extensions: Filtrar links por extensão (ex: ['pdf', 'xlsx'])

        Returns:
            CrawlResult com links encontrados
        """
        try:
            response = await self._fetch_with_retry(url)
            html = response.text

            # Parse HTML
            soup = BeautifulSoup(html, 'lxml')

            # Extrair links de <a href>
            links = []
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                absolute_url = urljoin(url, href)

                # Filtrar por extensão se especificado
                if file_extensions:
                    if any(absolute_url.lower().endswith(f".{ext}") for ext in file_extensions):
                        links.append(absolute_url)
                else:
                    links.append(absolute_url)

            # Remover duplicatas mantendo ordem
            links = list(dict.fromkeys(links))

            return CrawlResult(
                url=url,
                links=links,
                html_content=html,
                status_code=response.status_code,
            )

        except (CrawlerTimeoutError, CrawlerConnectionError, CrawlerError):
            raise
        except Exception as e:
            logger.error(f"Error crawling {url}: {e}", exc_info=True)
            raise CrawlerError(f"Failed to crawl {url}: {e}") from e

    async def download_file(
        self,
        url: str,
        destination: Path,
        timeout_seconds: Optional[int] = None
    ) -> DownloadResult:
        """
        Download arquivo com streaming

        Args:
            url: URL do arquivo
            destination: Caminho de destino
            timeout_seconds: Timeout customizado

        Returns:
            DownloadResult com informações do download
        """
        try:
            # Garantir que o diretório pai existe
            destination.parent.mkdir(parents=True, exist_ok=True)

            await self._apply_rate_limit(url)

            # Download com streaming para evitar carregar tudo na memória
            async with self.client.stream(
                "GET",
                url,
                timeout=timeout_seconds or self.timeout_seconds
            ) as response:
                response.raise_for_status()

                file_size = 0
                with open(destination, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        file_size += len(chunk)

                content_type = response.headers.get('content-type')

                return DownloadResult(
                    url=url,
                    file_path=destination,
                    file_size_bytes=file_size,
                    content_type=content_type,
                    success=True,
                )

        except httpx.TimeoutException as e:
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

    async def extract_assets(
        self,
        url: str,
        asset_types: List[AssetType]
    ) -> Dict[AssetType, List[str]]:
        """
        Extrai URLs de assets (CSS, JS, images, etc.)

        Args:
            url: URL da página
            asset_types: Tipos de assets para extrair

        Returns:
            Dict mapeando AssetType -> lista de URLs
        """
        try:
            response = await self._fetch_with_retry(url)
            html = response.text
            soup = BeautifulSoup(html, 'lxml')

            assets: Dict[AssetType, List[str]] = {asset_type: [] for asset_type in asset_types}

            # CSS - <link rel="stylesheet">
            if AssetType.CSS in asset_types:
                for link in soup.find_all('link', rel='stylesheet', href=True):
                    assets[AssetType.CSS].append(urljoin(url, link['href']))

            # JS - <script src>
            if AssetType.JS in asset_types:
                for script in soup.find_all('script', src=True):
                    assets[AssetType.JS].append(urljoin(url, script['src']))

            # Images - <img src>
            if AssetType.IMAGES in asset_types:
                for img in soup.find_all('img', src=True):
                    assets[AssetType.IMAGES].append(urljoin(url, img['src']))
                # Também pegar srcset
                for img in soup.find_all('img', srcset=True):
                    srcset = img['srcset']
                    # Parse srcset: "url1 1x, url2 2x"
                    for item in srcset.split(','):
                        src_url = item.strip().split()[0]
                        assets[AssetType.IMAGES].append(urljoin(url, src_url))

            # Fonts - @font-face em CSS inline
            # TODO: Parse CSS files para extrair fonts (complexo)

            # Videos - <video>, <source>
            if AssetType.VIDEOS in asset_types:
                for video in soup.find_all('video', src=True):
                    assets[AssetType.VIDEOS].append(urljoin(url, video['src']))
                for source in soup.find_all('source', src=True):
                    assets[AssetType.VIDEOS].append(urljoin(url, source['src']))

            # Remover duplicatas
            for asset_type in assets:
                assets[asset_type] = list(dict.fromkeys(assets[asset_type]))

            return assets

        except Exception as e:
            logger.error(f"Error extracting assets from {url}: {e}", exc_info=True)
            raise CrawlerError(f"Failed to extract assets: {e}") from e

    async def download_assets(
        self,
        asset_urls: Dict[AssetType, List[str]],
        destination_folder: Path,
        max_concurrent: int = 10
    ) -> Dict[str, DownloadResult]:
        """
        Download assets em paralelo

        Args:
            asset_urls: Dict com AssetType -> lista de URLs
            destination_folder: Pasta de destino
            max_concurrent: Máximo de downloads simultâneos

        Returns:
            Dict mapeando URL -> DownloadResult
        """
        results: Dict[str, DownloadResult] = {}

        # Criar tarefas de download
        tasks = []
        for asset_type, urls in asset_urls.items():
            # Criar subpasta para cada tipo
            type_folder = destination_folder / asset_type.value.lower()
            type_folder.mkdir(parents=True, exist_ok=True)

            for url in urls:
                # Extrair nome do arquivo da URL
                filename = Path(urlparse(url).path).name or "asset"
                file_path = type_folder / filename

                tasks.append(self._download_asset(url, file_path, results))

        # Executar downloads com limite de concorrência
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
        """Helper para download de asset com registro em results"""
        result = await self.download_file(url, destination)
        results[url] = result

    async def close(self):
        """Fecha httpx client"""
        await self.client.aclose()
        logger.info("BeautifulSoup crawler client closed")
