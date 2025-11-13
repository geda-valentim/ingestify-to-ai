"""
Crawler Port - Interface for web crawling

Abstração para motores de crawler (BeautifulSoup, Playwright, etc.)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from domain.value_objects.crawler_enums import AssetType


@dataclass
class CrawlResult:
    """Resultado de um crawl de página"""
    url: str
    links: List[str] = field(default_factory=list)
    assets: Dict[AssetType, List[str]] = field(default_factory=dict)
    html_content: Optional[str] = None
    status_code: int = 200
    error: Optional[str] = None

    @property
    def link_count(self) -> int:
        """Retorna contagem de links encontrados"""
        return len(self.links)

    @property
    def asset_count(self) -> int:
        """Retorna contagem total de assets"""
        return sum(len(urls) for urls in self.assets.values())


@dataclass
class DownloadResult:
    """Resultado de um download de arquivo"""
    url: str
    file_path: Path
    file_size_bytes: int
    content_type: Optional[str] = None
    success: bool = True
    error: Optional[str] = None


class CrawlerPort(ABC):
    """
    Interface para crawler de páginas web

    Implementações podem usar BeautifulSoup (HTTP simples),
    Playwright (JS rendering), Scrapy, etc.
    """

    @abstractmethod
    async def crawl_page(
        self,
        url: str,
        file_extensions: Optional[List[str]] = None
    ) -> CrawlResult:
        """
        Crawl uma página e extrai links

        Args:
            url: URL da página
            file_extensions: Lista de extensões para filtrar (ex: ['pdf', 'xlsx'])
                           Se None, retorna todos os links

        Returns:
            CrawlResult com links encontrados

        Raises:
            CrawlerError: Se crawl falhar
        """
        pass

    @abstractmethod
    async def download_file(
        self,
        url: str,
        destination: Path,
        timeout_seconds: Optional[int] = None
    ) -> DownloadResult:
        """
        Download de arquivo

        Args:
            url: URL do arquivo
            destination: Caminho de destino
            timeout_seconds: Timeout do download (None = usar padrão)

        Returns:
            DownloadResult com informações do download

        Raises:
            CrawlerError: Se download falhar
        """
        pass

    @abstractmethod
    async def extract_assets(
        self,
        url: str,
        asset_types: List[AssetType]
    ) -> Dict[AssetType, List[str]]:
        """
        Extrai URLs de assets de uma página (CSS, JS, images, etc.)

        Args:
            url: URL da página
            asset_types: Tipos de assets para extrair

        Returns:
            Dict mapeando AssetType para lista de URLs
            Exemplo: {AssetType.CSS: ['style.css'], AssetType.JS: ['app.js']}

        Raises:
            CrawlerError: Se extração falhar
        """
        pass

    @abstractmethod
    async def download_assets(
        self,
        asset_urls: Dict[AssetType, List[str]],
        destination_folder: Path,
        max_concurrent: int = 10
    ) -> Dict[str, DownloadResult]:
        """
        Download de múltiplos assets em paralelo

        Args:
            asset_urls: Dict com AssetType -> lista de URLs
            destination_folder: Pasta de destino (cria subpastas por tipo)
            max_concurrent: Máximo de downloads simultâneos

        Returns:
            Dict mapeando URL -> DownloadResult

        Raises:
            CrawlerError: Se downloads falharem
        """
        pass

    @abstractmethod
    async def close(self):
        """
        Fecha conexões e libera recursos

        Deve ser chamado ao finalizar uso do crawler
        """
        pass


class CrawlerError(Exception):
    """Erro durante crawling"""
    pass


class CrawlerTimeoutError(CrawlerError):
    """Timeout durante crawling"""
    pass


class CrawlerConnectionError(CrawlerError):
    """Erro de conexão durante crawling"""
    pass
