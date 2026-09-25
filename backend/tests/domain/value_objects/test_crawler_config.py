"""
Tests for CrawlerConfig value object
"""
import pytest
from domain.value_objects.crawler_config import CrawlerConfig, RetryStep
from domain.value_objects.crawler_enums import CrawlerMode, CrawlerEngine, AssetType
from domain.value_objects.proxy_config import ProxyConfig


def test_crawler_config_creation():
    """Test creating basic crawler config"""
    config = CrawlerConfig(
        mode=CrawlerMode.PAGE_ONLY,
        crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
    )

    assert config.mode == CrawlerMode.PAGE_ONLY
    assert config.crawler_engine == CrawlerEngine.BEAUTIFULSOUP
    assert config.use_proxy is False
    assert config.max_depth == 3


def test_crawler_config_page_with_filtered_requires_assets():
    """Test that PAGE_WITH_FILTERED mode requires asset_types"""
    with pytest.raises(ValueError, match="requires at least one asset type"):
        CrawlerConfig(
            mode=CrawlerMode.PAGE_WITH_FILTERED,
            crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
            asset_types=[],  # Empty list
        )


def test_crawler_config_page_only_rejects_assets():
    """Test that PAGE_ONLY should not have asset_types"""
    with pytest.raises(ValueError, match="should not have asset_types"):
        CrawlerConfig(
            mode=CrawlerMode.PAGE_ONLY,
            crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
            asset_types=[AssetType.CSS],
        )


def test_crawler_config_use_proxy_requires_config():
    """Test that use_proxy=True requires proxy_config"""
    with pytest.raises(ValueError, match="requires proxy_config"):
        CrawlerConfig(
            mode=CrawlerMode.PAGE_ONLY,
            crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
            use_proxy=True,
            proxy_config=None,
        )


def test_crawler_config_proxy_config_requires_use_proxy():
    """Test that proxy_config requires use_proxy=True"""
    proxy = ProxyConfig(host="proxy.example.com", port=8080)

    with pytest.raises(ValueError, match="should only be set when use_proxy=True"):
        CrawlerConfig(
            mode=CrawlerMode.PAGE_ONLY,
            crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
            use_proxy=False,
            proxy_config=proxy,
        )


def test_crawler_config_retry_strategy_priorities():
    """Test that retry strategy priorities must be sequential"""
    # Valid: 1, 2, 3
    config = CrawlerConfig(
        mode=CrawlerMode.PAGE_ONLY,
        crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
        retry_strategy=[
            RetryStep(1, CrawlerEngine.BEAUTIFULSOUP, False),
            RetryStep(2, CrawlerEngine.PLAYWRIGHT, False),
            RetryStep(3, CrawlerEngine.PLAYWRIGHT, True),
        ],
    )
    assert len(config.retry_strategy) == 3

    # Invalid: 1, 2, 4 (skips 3)
    with pytest.raises(ValueError, match="must be sequential"):
        CrawlerConfig(
            mode=CrawlerMode.PAGE_ONLY,
            crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
            retry_strategy=[
                RetryStep(1, CrawlerEngine.BEAUTIFULSOUP, False),
                RetryStep(2, CrawlerEngine.PLAYWRIGHT, False),
                RetryStep(4, CrawlerEngine.PLAYWRIGHT, True),  # Skip 3
            ],
        )


def test_crawler_config_serialization():
    """Test JSON serialization"""
    proxy = ProxyConfig(host="proxy.example.com", port=8080, protocol="http")

    config = CrawlerConfig(
        mode=CrawlerMode.PAGE_WITH_FILTERED,
        crawler_engine=CrawlerEngine.PLAYWRIGHT,
        asset_types=[AssetType.CSS, AssetType.JS],
        use_proxy=True,
        proxy_config=proxy,
        max_depth=5,
        follow_external_links=True,
        retry_strategy=[
            RetryStep(1, CrawlerEngine.BEAUTIFULSOUP, False),
            RetryStep(2, CrawlerEngine.PLAYWRIGHT, True),
        ],
    )

    data = config.to_dict()

    assert data["mode"] == "page_with_filtered"
    assert data["crawler_engine"] == "playwright"
    assert data["asset_types"] == ["css", "js"]
    assert data["use_proxy"] is True
    assert data["proxy_config"] is not None
    assert data["max_depth"] == 5
    assert data["follow_external_links"] is True
    assert len(data["retry_strategy"]) == 2


def test_crawler_config_deserialization():
    """Test JSON deserialization"""
    data = {
        "mode": "page_only",
        "crawler_engine": "beautifulsoup",
        "asset_types": [],
        "use_proxy": False,
        "proxy_config": None,
        "max_depth": 3,
        "follow_external_links": False,
        "retry_strategy": [],
    }

    config = CrawlerConfig.from_dict(data)

    assert config.mode == CrawlerMode.PAGE_ONLY
    assert config.crawler_engine == CrawlerEngine.BEAUTIFULSOUP
    assert config.asset_types == []
    assert config.use_proxy is False
    assert config.max_depth == 3


def test_crawler_config_default():
    """Test default factory method"""
    config = CrawlerConfig.default()

    assert config.mode == CrawlerMode.PAGE_ONLY
    assert config.crawler_engine == CrawlerEngine.BEAUTIFULSOUP
    assert config.use_proxy is False
    assert config.proxy_config is None


def test_crawler_config_with_retry():
    """Test with_retry factory method"""
    proxy = ProxyConfig(host="proxy.example.com", port=8080)

    config = CrawlerConfig.with_retry(
        mode=CrawlerMode.PAGE_ONLY,
        proxy_config=proxy,
    )

    assert config.mode == CrawlerMode.PAGE_ONLY
    assert len(config.retry_strategy) == 4  # 4 attempts with proxy
    assert config.retry_strategy[0].priority == 1
    assert config.retry_strategy[0].engine == CrawlerEngine.BEAUTIFULSOUP
    assert config.retry_strategy[0].use_proxy is False


def test_crawler_config_get_engine_for_attempt():
    """Test getting engine for attempt number"""
    config = CrawlerConfig.with_retry()

    engine1, proxy1 = config.get_engine_for_attempt(1)
    assert engine1 == CrawlerEngine.BEAUTIFULSOUP
    assert proxy1 is False

    engine2, proxy2 = config.get_engine_for_attempt(2)
    assert engine2 == CrawlerEngine.PLAYWRIGHT
    assert proxy2 is False
