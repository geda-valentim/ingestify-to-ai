"""
Tests for Proxy Manager
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx

from infrastructure.adapters.proxy_manager import ProxyManager, ProxyPool
from domain.value_objects.proxy_config import ProxyConfig
from application.ports.crawler_port import CrawlerError


class TestProxyFormatConversion:
    """Testes de conversão de formato de proxy"""

    def test_to_httpx_format(self):
        """Teste: Conversão para formato httpx"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
        )

        result = ProxyManager.to_httpx_format(proxy)

        assert result == "http://proxy.example.com:8080"

    def test_to_httpx_format_with_auth(self):
        """Teste: Conversão para httpx com autenticação"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
            username="user",
            password="pass",
        )

        result = ProxyManager.to_httpx_format(proxy)

        # URL deve conter credenciais
        assert result == "http://user:pass@proxy.example.com:8080"

    def test_to_playwright_format(self):
        """Teste: Conversão para formato Playwright"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
        )

        result = ProxyManager.to_playwright_format(proxy)

        assert result == {
            "server": "http://proxy.example.com:8080"
        }

    def test_to_playwright_format_with_auth(self):
        """Teste: Conversão para Playwright com autenticação"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
            username="user",
            password="pass",
        )

        result = ProxyManager.to_playwright_format(proxy)

        assert result["server"] == "http://proxy.example.com:8080"
        assert result["username"] == "user"
        assert result["password"] == "pass"


class TestProxyTesting:
    """Testes de validação de proxy"""

    @pytest.mark.asyncio
    async def test_test_proxy_success(self):
        """Teste: Proxy funcionando"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
        )

        with patch('infrastructure.adapters.proxy_manager.httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)

            result = await ProxyManager.test_proxy(proxy)

            assert result is True

    @pytest.mark.asyncio
    async def test_test_proxy_timeout(self):
        """Teste: Proxy com timeout"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
        )

        with patch('infrastructure.adapters.proxy_manager.httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = httpx.TimeoutException("Timeout")

            result = await ProxyManager.test_proxy(proxy)

            assert result is False

    @pytest.mark.asyncio
    async def test_test_proxy_connection_error(self):
        """Teste: Proxy com erro de conexão"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
        )

        with patch('infrastructure.adapters.proxy_manager.httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = httpx.ConnectError("Connection failed")

            result = await ProxyManager.test_proxy(proxy)

            assert result is False


class TestProxyValidation:
    """Testes de validação de configuração"""

    def test_validate_proxy_config_valid(self):
        """Teste: Configuração válida"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="http",
        )

        # Não deve lançar exceção
        ProxyManager.validate_proxy_config(proxy)

    def test_validate_proxy_config_invalid_port(self):
        """Teste: Porta inválida - ProxyConfig já valida no __post_init__"""
        # ProxyConfig já valida a porta no __post_init__, então não conseguimos criar com porta inválida
        with pytest.raises(ValueError, match="Port must be between"):
            proxy = ProxyConfig(
                host="proxy.example.com",
                port=99999,  # Porta inválida
                protocol="http",
            )

    def test_validate_proxy_config_invalid_protocol(self):
        """Teste: Protocolo inválido"""
        # Nota: ProxyConfig já valida protocolo no __post_init__
        # Este teste verifica validação adicional no ProxyManager

        proxy = Mock()
        proxy.host = "proxy.example.com"
        proxy.port = 8080
        proxy.protocol = "invalid"
        proxy.username = None
        proxy.password = None

        with pytest.raises(CrawlerError, match="Invalid proxy protocol"):
            ProxyManager.validate_proxy_config(proxy)


class TestProxyPool:
    """Testes de pool de proxies (future feature)"""

    def test_proxy_pool_init(self):
        """Teste: Inicialização do pool"""
        proxies = [
            ProxyConfig(host="proxy1.com", port=8080, protocol="http"),
            ProxyConfig(host="proxy2.com", port=8080, protocol="http"),
        ]

        pool = ProxyPool(proxies)

        assert len(pool.proxies) == 2
        assert pool.current_index == 0

    def test_get_next_proxy_round_robin(self):
        """Teste: Rotação round-robin"""
        proxies = [
            ProxyConfig(host="proxy1.com", port=8080, protocol="http"),
            ProxyConfig(host="proxy2.com", port=8080, protocol="http"),
            ProxyConfig(host="proxy3.com", port=8080, protocol="http"),
        ]

        pool = ProxyPool(proxies)

        proxy1 = pool.get_next_proxy(strategy="round_robin")
        assert proxy1.host == "proxy1.com"

        proxy2 = pool.get_next_proxy(strategy="round_robin")
        assert proxy2.host == "proxy2.com"

        proxy3 = pool.get_next_proxy(strategy="round_robin")
        assert proxy3.host == "proxy3.com"

        # Deve voltar ao primeiro
        proxy4 = pool.get_next_proxy(strategy="round_robin")
        assert proxy4.host == "proxy1.com"

    def test_get_next_proxy_random(self):
        """Teste: Rotação aleatória"""
        proxies = [
            ProxyConfig(host="proxy1.com", port=8080, protocol="http"),
            ProxyConfig(host="proxy2.com", port=8080, protocol="http"),
        ]

        pool = ProxyPool(proxies)

        # Obter 10 proxies aleatórios
        random_proxies = [pool.get_next_proxy(strategy="random") for _ in range(10)]

        # Verificar que todos estão no pool
        for proxy in random_proxies:
            assert proxy.host in ["proxy1.com", "proxy2.com"]

    @pytest.mark.asyncio
    async def test_test_all_proxies(self):
        """Teste: Testar todos os proxies do pool"""
        proxies = [
            ProxyConfig(host="proxy1.com", port=8080, protocol="http"),
            ProxyConfig(host="proxy2.com", port=8080, protocol="http"),
        ]

        pool = ProxyPool(proxies)

        with patch.object(ProxyManager, 'test_proxy', new_callable=AsyncMock) as mock_test:
            mock_test.side_effect = [True, False]  # Primeiro funciona, segundo não

            results = await pool.test_all_proxies()

            assert results["proxy1.com:8080"] is True
            assert results["proxy2.com:8080"] is False
            assert mock_test.call_count == 2
