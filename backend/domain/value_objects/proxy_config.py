"""
ProxyConfig Value Object - Proxy server configuration
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProxyConfig:
    """
    Value Object for proxy server configuration.

    Immutable proxy settings for web scraping/crawling.
    Supports HTTP, HTTPS, and SOCKS5 proxies.
    """
    host: str
    port: int
    protocol: str = "http"  # http, https, socks5
    username: Optional[str] = None
    password: Optional[str] = None

    def __post_init__(self):
        """Validate proxy configuration"""
        self._validate_protocol()
        self._validate_port()
        self._validate_host()
        self._validate_auth()

    def _validate_protocol(self):
        """Validate protocol is supported"""
        valid_protocols = ["http", "https", "socks5"]
        if self.protocol.lower() not in valid_protocols:
            raise ValueError(
                f"Invalid protocol '{self.protocol}'. Must be one of: {', '.join(valid_protocols)}"
            )

    def _validate_port(self):
        """Validate port is in valid range"""
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {self.port}")

    def _validate_host(self):
        """Validate host is not empty"""
        if not self.host or not self.host.strip():
            raise ValueError("Proxy host cannot be empty")

    def _validate_auth(self):
        """Validate auth credentials are both present or both absent"""
        if (self.username is None) != (self.password is None):
            raise ValueError("Both username and password must be provided together, or neither")

    @property
    def requires_auth(self) -> bool:
        """Check if proxy requires authentication"""
        return self.username is not None and self.password is not None

    @property
    def url(self) -> str:
        """
        Build proxy URL.

        Returns:
            Proxy URL string (e.g., "http://user:pass@proxy.example.com:8080")
        """
        if self.requires_auth:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "username": self.username,
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProxyConfig":
        """
        Create ProxyConfig from dictionary.

        Args:
            data: Dictionary with proxy config keys

        Returns:
            ProxyConfig instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        if not isinstance(data, dict):
            raise ValueError("Input must be a dictionary")

        required_fields = ["host", "port"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        return cls(
            host=data["host"],
            port=data["port"],
            protocol=data.get("protocol", "http"),
            username=data.get("username"),
            password=data.get("password"),
        )

    @classmethod
    def from_url(cls, proxy_url: str) -> "ProxyConfig":
        """
        Parse proxy URL into ProxyConfig.

        Args:
            proxy_url: Proxy URL (e.g., "http://user:pass@proxy.example.com:8080")

        Returns:
            ProxyConfig instance

        Raises:
            ValueError: If URL format is invalid
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(proxy_url)
        except Exception as e:
            raise ValueError(f"Invalid proxy URL: {e}")

        if not parsed.hostname:
            raise ValueError("Proxy URL must contain hostname")

        if not parsed.port:
            raise ValueError("Proxy URL must contain port")

        return cls(
            host=parsed.hostname,
            port=parsed.port,
            protocol=parsed.scheme or "http",
            username=parsed.username,
            password=parsed.password,
        )

    def __str__(self) -> str:
        """String representation (without credentials)"""
        return f"{self.protocol}://{self.host}:{self.port}"
