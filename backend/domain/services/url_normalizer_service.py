"""
URL Normalizer Service - Domain logic for normalizing URLs

Normalizes URLs for consistent comparison and pattern matching.
Used for detecting duplicate crawlers with similar URLs.
"""
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Optional
import re


class URLNormalizerService:
    """
    Domain service for URL normalization and pattern generation.

    Provides consistent URL normalization for:
    - Exact matching (detecting identical URLs)
    - Fuzzy matching (detecting similar URLs with different parameters)
    """

    # Private IP ranges (RFC 1918)
    PRIVATE_IP_PATTERNS = [
        r'^10\.',
        r'^172\.(1[6-9]|2[0-9]|3[0-1])\.',
        r'^192\.168\.',
    ]

    # Localhost patterns
    LOCALHOST_PATTERNS = [
        r'^localhost$',
        r'^127\.',
        r'^::1$',
        r'^0\.0\.0\.0$',
    ]

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normalize URL for exact comparison.

        Normalization steps:
        1. Convert scheme and domain to lowercase
        2. Remove default ports (80 for http, 443 for https)
        3. Remove trailing slash from path (unless it's the root)
        4. Sort query parameters alphabetically
        5. Remove fragment (#)

        Args:
            url: URL to normalize

        Returns:
            Normalized URL string

        Raises:
            ValueError: If URL is invalid or empty

        Example:
            >>> normalize_url("HTTPS://Example.com:443/Path?z=1&a=2#section")
            'https://example.com/Path?a=2&z=1'
        """
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        try:
            parsed = urlparse(url)
        except Exception as e:
            raise ValueError(f"Invalid URL: {e}")

        # Validate required components
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"URL must have scheme and domain: {url}")

        # Normalize scheme and domain
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Remove default ports
        if ':' in netloc:
            domain, port = netloc.rsplit(':', 1)
            if (scheme == 'http' and port == '80') or (scheme == 'https' and port == '443'):
                netloc = domain

        # Normalize path
        path = parsed.path or '/'
        # Remove trailing slash (except for root)
        if path != '/' and path.endswith('/'):
            path = path.rstrip('/')

        # Sort query parameters
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            # Sort parameters alphabetically
            sorted_params = sorted(params.items())
            query = urlencode(sorted_params, doseq=True)
        else:
            query = ''

        # Reconstruct URL without fragment
        normalized = urlunparse((scheme, netloc, path, parsed.params, query, ''))

        return normalized

    @staticmethod
    def generate_pattern(url: str) -> str:
        """
        Generate pattern for fuzzy URL matching.

        Replaces query parameter values with wildcards (*) to detect
        URLs with same structure but different parameter values.

        Args:
            url: URL to generate pattern from

        Returns:
            Pattern string for fuzzy matching

        Raises:
            ValueError: If URL is invalid

        Example:
            >>> generate_pattern("https://example.com/page?id=123&sort=desc")
            'https://example.com/page?id=*&sort=*'
        """
        # First normalize the URL
        normalized = URLNormalizerService.normalize_url(url)

        try:
            parsed = urlparse(normalized)
        except Exception as e:
            raise ValueError(f"Invalid URL: {e}")

        # Replace query parameter values with wildcards
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            # Replace all values with *
            wildcard_params = {key: '*' for key in params.keys()}
            # Sort parameters alphabetically
            sorted_params = sorted(wildcard_params.items())
            # Use safe='*' to prevent encoding of wildcard character
            query = urlencode(sorted_params, safe='*')
        else:
            query = ''

        # Reconstruct URL with wildcard params
        pattern = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, ''))

        return pattern

    @staticmethod
    def is_localhost(url: str) -> bool:
        """
        Check if URL points to localhost or private IP.

        Args:
            url: URL to check

        Returns:
            True if URL is localhost/private IP

        Example:
            >>> is_localhost("http://localhost:8080/page")
            True
            >>> is_localhost("http://192.168.1.1/admin")
            True
            >>> is_localhost("https://example.com")
            False
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or parsed.netloc

            if not hostname:
                return False

            hostname = hostname.lower()

            # Check localhost patterns
            for pattern in URLNormalizerService.LOCALHOST_PATTERNS:
                if re.match(pattern, hostname):
                    return True

            # Check private IP patterns
            for pattern in URLNormalizerService.PRIVATE_IP_PATTERNS:
                if re.match(pattern, hostname):
                    return True

            return False

        except Exception:
            return False

    @staticmethod
    def extract_domain(url: str) -> str:
        """
        Extract domain from URL.

        Args:
            url: URL to extract domain from

        Returns:
            Domain string (e.g., "example.com")

        Raises:
            ValueError: If URL is invalid

        Example:
            >>> extract_domain("https://subdomain.example.com:8080/path")
            'subdomain.example.com'
        """
        try:
            parsed = urlparse(url)
            # Remove port if present
            domain = parsed.hostname or parsed.netloc.split(':')[0]
            return domain.lower()
        except Exception as e:
            raise ValueError(f"Invalid URL: {e}")

    @staticmethod
    def validate_url(url: str, allow_localhost: bool = False) -> bool:
        """
        Validate URL for crawler usage.

        Checks:
        - Valid scheme (http/https)
        - Has domain
        - Not localhost/private IP (unless allow_localhost=True)

        Args:
            url: URL to validate
            allow_localhost: Whether to allow localhost/private IPs

        Returns:
            True if URL is valid for crawling

        Example:
            >>> validate_url("https://example.com")
            True
            >>> validate_url("http://localhost")
            False
            >>> validate_url("http://localhost", allow_localhost=True)
            True
        """
        if not url or not url.strip():
            return False

        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in ['http', 'https']:
                return False

            # Check domain exists
            if not parsed.netloc:
                return False

            # Check for localhost/private IP
            if not allow_localhost and URLNormalizerService.is_localhost(url):
                return False

            return True

        except Exception:
            return False

    @staticmethod
    def are_urls_similar(url1: str, url2: str) -> bool:
        """
        Check if two URLs have the same pattern (ignoring parameter values).

        Args:
            url1: First URL
            url2: Second URL

        Returns:
            True if URLs have same pattern

        Example:
            >>> are_urls_similar(
            ...     "https://example.com/page?id=123",
            ...     "https://example.com/page?id=456"
            ... )
            True
        """
        try:
            pattern1 = URLNormalizerService.generate_pattern(url1)
            pattern2 = URLNormalizerService.generate_pattern(url2)
            return pattern1 == pattern2
        except ValueError:
            return False
