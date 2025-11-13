"""
Proxy Manager

Gerenciamento de proxies para crawlers
"""
import logging
from typing import Optional, Dict, Any
import httpx

from domain.value_objects.proxy_config import ProxyConfig
from application.ports.crawler_port import CrawlerError

logger = logging.getLogger(__name__)


class ProxyManager:
    """
    Gerenciador de proxies para adapters de crawler

    Funcionalidades:
    - Conversão de ProxyConfig para formatos específicos (httpx, Playwright)
    - Teste de conectividade de proxy
    - (Future) Pool de proxies com rotação
    """

    @staticmethod
    def to_httpx_format(proxy_config: ProxyConfig) -> str:
        """
        Converte ProxyConfig para formato httpx

        Args:
            proxy_config: Configuração do proxy

        Returns:
            URL do proxy para httpx.AsyncClient

        Example:
            proxy = ProxyManager.to_httpx_format(proxy_config)
            client = httpx.AsyncClient(proxy=proxy)
        """
        return proxy_config.url

    @staticmethod
    def to_playwright_format(proxy_config: ProxyConfig) -> Dict[str, Any]:
        """
        Converte ProxyConfig para formato Playwright

        Args:
            proxy_config: Configuração do proxy

        Returns:
            Dict para passar no Browser.launch(proxy=...)

        Example:
            proxy = ProxyManager.to_playwright_format(proxy_config)
            browser = await playwright.chromium.launch(proxy=proxy)
        """
        proxy_dict = {
            "server": f"{proxy_config.protocol}://{proxy_config.host}:{proxy_config.port}"
        }

        # Adicionar autenticação se configurada
        if proxy_config.username and proxy_config.password:
            proxy_dict["username"] = proxy_config.username
            proxy_dict["password"] = proxy_config.password

        return proxy_dict

    @staticmethod
    async def test_proxy(
        proxy_config: ProxyConfig,
        test_url: str = "https://httpbin.org/ip",
        timeout_seconds: int = 10
    ) -> bool:
        """
        Testa conectividade do proxy

        Args:
            proxy_config: Configuração do proxy
            test_url: URL para testar (padrão: httpbin.org/ip)
            timeout_seconds: Timeout do teste

        Returns:
            True se proxy está funcionando, False caso contrário
        """
        proxy = ProxyManager.to_httpx_format(proxy_config)

        try:
            async with httpx.AsyncClient(
                proxy=proxy,
                timeout=httpx.Timeout(timeout_seconds)
            ) as client:
                response = await client.get(test_url)
                response.raise_for_status()

                logger.info(f"Proxy {proxy_config.host}:{proxy_config.port} is working")
                return True

        except httpx.TimeoutException:
            logger.warning(f"Proxy {proxy_config.host}:{proxy_config.port} timeout")
            return False

        except httpx.ConnectError as e:
            logger.warning(f"Proxy {proxy_config.host}:{proxy_config.port} connection error: {e}")
            return False

        except httpx.HTTPStatusError as e:
            logger.warning(f"Proxy {proxy_config.host}:{proxy_config.port} HTTP error: {e}")
            return False

        except Exception as e:
            logger.error(f"Proxy {proxy_config.host}:{proxy_config.port} test failed: {e}")
            return False

    @staticmethod
    def validate_proxy_config(proxy_config: ProxyConfig) -> None:
        """
        Valida configuração de proxy

        Args:
            proxy_config: Configuração do proxy

        Raises:
            CrawlerError: Se configuração inválida
        """
        # Validações básicas (ProxyConfig já valida no __post_init__)
        if not proxy_config.host:
            raise CrawlerError("Proxy host cannot be empty")

        if proxy_config.port < 1 or proxy_config.port > 65535:
            raise CrawlerError(f"Invalid proxy port: {proxy_config.port}")

        if proxy_config.protocol not in ["http", "https", "socks5"]:
            raise CrawlerError(f"Invalid proxy protocol: {proxy_config.protocol}")

        # Validar autenticação
        if proxy_config.username and not proxy_config.password:
            raise CrawlerError("Proxy username requires password")

        if proxy_config.password and not proxy_config.username:
            raise CrawlerError("Proxy password requires username")


# Future: Proxy Pool para rotação
class ProxyPool:
    """
    Pool de proxies com rotação

    TODO: Implementar em sprint futuro para suporte a múltiplos proxies
    """

    def __init__(self, proxies: list[ProxyConfig]):
        """
        Inicializa pool de proxies

        Args:
            proxies: Lista de ProxyConfig
        """
        self.proxies = proxies
        self.current_index = 0

    def get_next_proxy(self, strategy: str = "round_robin") -> ProxyConfig:
        """
        Retorna próximo proxy do pool

        Args:
            strategy: Estratégia de rotação (round_robin, random)

        Returns:
            ProxyConfig
        """
        if strategy == "round_robin":
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            return proxy

        elif strategy == "random":
            import random
            return random.choice(self.proxies)

        else:
            raise ValueError(f"Unknown proxy rotation strategy: {strategy}")

    async def test_all_proxies(self, test_url: str = "https://httpbin.org/ip") -> Dict[str, bool]:
        """
        Testa todos os proxies do pool

        Args:
            test_url: URL para testar

        Returns:
            Dict mapeando proxy URL -> status (True/False)
        """
        results = {}

        for proxy in self.proxies:
            proxy_key = f"{proxy.host}:{proxy.port}"
            is_working = await ProxyManager.test_proxy(proxy, test_url)
            results[proxy_key] = is_working

        return results
