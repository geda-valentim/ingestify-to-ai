"""
Tests for URLNormalizerService
"""
import pytest
from domain.services.url_normalizer_service import URLNormalizerService


def test_normalize_url_basic():
    """Test basic URL normalization"""
    url = "https://Example.COM/Path"
    normalized = URLNormalizerService.normalize_url(url)

    assert normalized == "https://example.com/Path"


def test_normalize_url_removes_trailing_slash():
    """Test that trailing slash is removed (except root)"""
    url1 = "https://example.com/path/"
    normalized1 = URLNormalizerService.normalize_url(url1)
    assert normalized1 == "https://example.com/path"

    # Root should keep slash
    url2 = "https://example.com/"
    normalized2 = URLNormalizerService.normalize_url(url2)
    assert normalized2 == "https://example.com/"


def test_normalize_url_sorts_query_params():
    """Test that query parameters are sorted alphabetically"""
    url = "https://example.com/page?z=1&a=2&m=3"
    normalized = URLNormalizerService.normalize_url(url)

    assert normalized == "https://example.com/page?a=2&m=3&z=1"


def test_normalize_url_removes_fragment():
    """Test that URL fragment is removed"""
    url = "https://example.com/page#section"
    normalized = URLNormalizerService.normalize_url(url)

    assert normalized == "https://example.com/page"


def test_normalize_url_removes_default_ports():
    """Test that default ports are removed"""
    url1 = "http://example.com:80/path"
    normalized1 = URLNormalizerService.normalize_url(url1)
    assert normalized1 == "http://example.com/path"

    url2 = "https://example.com:443/path"
    normalized2 = URLNormalizerService.normalize_url(url2)
    assert normalized2 == "https://example.com/path"

    # Non-default ports should be kept
    url3 = "https://example.com:8080/path"
    normalized3 = URLNormalizerService.normalize_url(url3)
    assert normalized3 == "https://example.com:8080/path"


def test_normalize_url_empty():
    """Test that empty URL raises ValueError"""
    with pytest.raises(ValueError, match="cannot be empty"):
        URLNormalizerService.normalize_url("")


def test_normalize_url_invalid():
    """Test that invalid URL raises ValueError"""
    with pytest.raises(ValueError):
        URLNormalizerService.normalize_url("not-a-url")


def test_generate_pattern():
    """Test URL pattern generation"""
    url = "https://example.com/page?id=123&sort=desc"
    pattern = URLNormalizerService.generate_pattern(url)

    assert pattern == "https://example.com/page?id=*&sort=*"


def test_generate_pattern_no_params():
    """Test pattern generation for URL without params"""
    url = "https://example.com/page"
    pattern = URLNormalizerService.generate_pattern(url)

    assert pattern == "https://example.com/page"


def test_is_localhost():
    """Test localhost detection"""
    # Localhost
    assert URLNormalizerService.is_localhost("http://localhost") is True
    assert URLNormalizerService.is_localhost("http://localhost:8080") is True
    assert URLNormalizerService.is_localhost("http://127.0.0.1") is True
    assert URLNormalizerService.is_localhost("http://127.0.0.1:3000") is True

    # Private IPs
    assert URLNormalizerService.is_localhost("http://192.168.1.1") is True
    assert URLNormalizerService.is_localhost("http://10.0.0.1") is True
    assert URLNormalizerService.is_localhost("http://172.16.0.1") is True

    # Public URLs
    assert URLNormalizerService.is_localhost("https://example.com") is False
    assert URLNormalizerService.is_localhost("https://google.com") is False


def test_extract_domain():
    """Test domain extraction"""
    url1 = "https://example.com/path"
    assert URLNormalizerService.extract_domain(url1) == "example.com"

    url2 = "https://subdomain.example.com:8080/path"
    assert URLNormalizerService.extract_domain(url2) == "subdomain.example.com"


def test_validate_url():
    """Test URL validation"""
    # Valid URLs
    assert URLNormalizerService.validate_url("https://example.com") is True
    assert URLNormalizerService.validate_url("http://example.com/path") is True

    # Invalid: localhost (unless allowed)
    assert URLNormalizerService.validate_url("http://localhost") is False
    assert URLNormalizerService.validate_url("http://localhost", allow_localhost=True) is True

    # Invalid: private IP (unless allowed)
    assert URLNormalizerService.validate_url("http://192.168.1.1") is False
    assert URLNormalizerService.validate_url("http://192.168.1.1", allow_localhost=True) is True

    # Invalid: wrong scheme
    assert URLNormalizerService.validate_url("ftp://example.com") is False

    # Invalid: empty
    assert URLNormalizerService.validate_url("") is False


def test_are_urls_similar():
    """Test URL similarity check"""
    url1 = "https://example.com/page?id=123"
    url2 = "https://example.com/page?id=456"

    # Same pattern - should be similar
    assert URLNormalizerService.are_urls_similar(url1, url2) is True

    url3 = "https://example.com/other?id=123"

    # Different path - not similar
    assert URLNormalizerService.are_urls_similar(url1, url3) is False
