"""
Tests for ProxyConfig value object
"""
import pytest
from domain.value_objects.proxy_config import ProxyConfig


def test_proxy_config_creation():
    """Test creating basic proxy config"""
    proxy = ProxyConfig(
        host="proxy.example.com",
        port=8080,
        protocol="http",
    )

    assert proxy.host == "proxy.example.com"
    assert proxy.port == 8080
    assert proxy.protocol == "http"
    assert proxy.username is None
    assert proxy.password is None


def test_proxy_config_with_auth():
    """Test proxy with authentication"""
    proxy = ProxyConfig(
        host="proxy.example.com",
        port=8080,
        username="user",
        password="pass",
    )

    assert proxy.requires_auth is True
    assert proxy.username == "user"
    assert proxy.password == "pass"


def test_proxy_config_invalid_protocol():
    """Test that invalid protocol raises ValueError"""
    with pytest.raises(ValueError, match="Invalid protocol"):
        ProxyConfig(
            host="proxy.example.com",
            port=8080,
            protocol="invalid",
        )


def test_proxy_config_invalid_port():
    """Test that invalid port raises ValueError"""
    with pytest.raises(ValueError, match="Port must be between"):
        ProxyConfig(
            host="proxy.example.com",
            port=99999,  # Invalid port
        )

    with pytest.raises(ValueError, match="Port must be between"):
        ProxyConfig(
            host="proxy.example.com",
            port=0,  # Invalid port
        )


def test_proxy_config_empty_host():
    """Test that empty host raises ValueError"""
    with pytest.raises(ValueError, match="cannot be empty"):
        ProxyConfig(
            host="",
            port=8080,
        )


def test_proxy_config_auth_must_be_both():
    """Test that username and password must both be provided"""
    # Only username
    with pytest.raises(ValueError, match="Both username and password"):
        ProxyConfig(
            host="proxy.example.com",
            port=8080,
            username="user",
            password=None,
        )

    # Only password
    with pytest.raises(ValueError, match="Both username and password"):
        ProxyConfig(
            host="proxy.example.com",
            port=8080,
            username=None,
            password="pass",
        )


def test_proxy_config_url_without_auth():
    """Test proxy URL generation without auth"""
    proxy = ProxyConfig(
        host="proxy.example.com",
        port=8080,
        protocol="http",
    )

    assert proxy.url == "http://proxy.example.com:8080"


def test_proxy_config_url_with_auth():
    """Test proxy URL generation with auth"""
    proxy = ProxyConfig(
        host="proxy.example.com",
        port=8080,
        protocol="http",
        username="user",
        password="pass",
    )

    assert proxy.url == "http://user:pass@proxy.example.com:8080"


def test_proxy_config_serialization():
    """Test JSON serialization"""
    proxy = ProxyConfig(
        host="proxy.example.com",
        port=8080,
        protocol="https",
        username="user",
        password="pass",
    )

    data = proxy.to_dict()

    assert data["host"] == "proxy.example.com"
    assert data["port"] == 8080
    assert data["protocol"] == "https"
    assert data["username"] == "user"
    assert data["password"] == "pass"


def test_proxy_config_deserialization():
    """Test JSON deserialization"""
    data = {
        "host": "proxy.example.com",
        "port": 8080,
        "protocol": "socks5",
        "username": "user",
        "password": "pass",
    }

    proxy = ProxyConfig.from_dict(data)

    assert proxy.host == "proxy.example.com"
    assert proxy.port == 8080
    assert proxy.protocol == "socks5"
    assert proxy.requires_auth is True


def test_proxy_config_from_url():
    """Test parsing from URL"""
    url = "http://user:pass@proxy.example.com:8080"

    proxy = ProxyConfig.from_url(url)

    assert proxy.host == "proxy.example.com"
    assert proxy.port == 8080
    assert proxy.protocol == "http"
    assert proxy.username == "user"
    assert proxy.password == "pass"


def test_proxy_config_from_url_without_auth():
    """Test parsing from URL without auth"""
    url = "https://proxy.example.com:3128"

    proxy = ProxyConfig.from_url(url)

    assert proxy.host == "proxy.example.com"
    assert proxy.port == 3128
    assert proxy.protocol == "https"
    assert proxy.requires_auth is False
