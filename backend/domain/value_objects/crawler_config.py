"""
CrawlerConfig Value Object - Crawler configuration settings
"""
from dataclasses import dataclass, field
from typing import Optional, List
from domain.value_objects.crawler_enums import CrawlerMode, CrawlerEngine, AssetType
from domain.value_objects.proxy_config import ProxyConfig


@dataclass(frozen=True)
class RetryStep:
    """
    Single retry step in the retry strategy.

    Defines which engine and proxy settings to use for a retry attempt.
    """
    priority: int  # 1 = first attempt, 2 = first retry, etc.
    engine: CrawlerEngine
    use_proxy: bool

    def __post_init__(self):
        """Validate retry step"""
        if self.priority < 1:
            raise ValueError(f"Priority must be >= 1, got {self.priority}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "priority": self.priority,
            "engine": self.engine.value,
            "use_proxy": self.use_proxy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetryStep":
        """Create RetryStep from dictionary"""
        return cls(
            priority=data["priority"],
            engine=CrawlerEngine(data["engine"]),
            use_proxy=data["use_proxy"],
        )


@dataclass(frozen=True)
class CrawlerConfig:
    """
    Value Object for crawler configuration.

    Immutable configuration for web crawling/scraping operations.
    Includes engine selection, asset filtering, retry strategy, and proxy settings.
    """
    mode: CrawlerMode
    crawler_engine: CrawlerEngine
    asset_types: List[AssetType] = field(default_factory=list)
    retry_strategy: List[RetryStep] = field(default_factory=list)
    use_proxy: bool = False
    proxy_config: Optional[ProxyConfig] = None
    max_depth: int = 3
    follow_external_links: bool = False

    def __post_init__(self):
        """Validate crawler configuration"""
        self._validate_mode_and_assets()
        self._validate_retry_strategy()
        self._validate_proxy()
        self._validate_depth()

    def _validate_mode_and_assets(self):
        """Validate that asset_types is non-empty if mode requires assets"""
        if self.mode in [CrawlerMode.PAGE_WITH_FILTERED] and not self.asset_types:
            raise ValueError(
                f"Mode '{self.mode.value}' requires at least one asset type"
            )

        if self.mode == CrawlerMode.PAGE_ONLY and self.asset_types:
            raise ValueError(
                f"Mode '{self.mode.value}' should not have asset_types specified"
            )

    def _validate_retry_strategy(self):
        """Validate retry strategy priorities are sequential"""
        if not self.retry_strategy:
            return  # Empty retry strategy is valid (no retries)

        priorities = [step.priority for step in self.retry_strategy]

        # Check for duplicates
        if len(priorities) != len(set(priorities)):
            raise ValueError("Retry strategy priorities must be unique")

        # Check priorities are sequential starting from 1
        sorted_priorities = sorted(priorities)
        expected_priorities = list(range(1, len(priorities) + 1))
        if sorted_priorities != expected_priorities:
            raise ValueError(
                f"Retry strategy priorities must be sequential starting from 1. "
                f"Expected {expected_priorities}, got {sorted_priorities}"
            )

    def _validate_proxy(self):
        """Validate proxy configuration consistency"""
        if self.use_proxy and self.proxy_config is None:
            raise ValueError("use_proxy=True requires proxy_config to be set")

        if not self.use_proxy and self.proxy_config is not None:
            raise ValueError("proxy_config should only be set when use_proxy=True")

    def _validate_depth(self):
        """Validate max_depth is positive"""
        if self.max_depth < 1:
            raise ValueError(f"max_depth must be >= 1, got {self.max_depth}")

    @property
    def downloads_assets(self) -> bool:
        """Check if this configuration downloads any assets"""
        return self.mode in [CrawlerMode.PAGE_WITH_ALL, CrawlerMode.PAGE_WITH_FILTERED]

    @property
    def crawls_multiple_pages(self) -> bool:
        """Check if this configuration crawls multiple pages"""
        return self.mode == CrawlerMode.FULL_WEBSITE

    @property
    def requires_proxy(self) -> bool:
        """Check if proxy is required for any retry attempt"""
        return self.use_proxy or any(step.use_proxy for step in self.retry_strategy)

    def get_engine_for_attempt(self, attempt_number: int) -> tuple[CrawlerEngine, bool]:
        """
        Get engine and proxy setting for a given attempt number.

        Args:
            attempt_number: Attempt number (1 = first attempt, 2 = first retry, etc.)

        Returns:
            Tuple of (engine, use_proxy)

        Raises:
            ValueError: If attempt number exceeds retry strategy
        """
        if attempt_number < 1:
            raise ValueError(f"Attempt number must be >= 1, got {attempt_number}")

        # If no retry strategy, use default for all attempts
        if not self.retry_strategy:
            return (self.crawler_engine, self.use_proxy)

        # Find matching retry step
        for step in self.retry_strategy:
            if step.priority == attempt_number:
                return (step.engine, step.use_proxy)

        # If attempt exceeds strategy, use last step
        last_step = max(self.retry_strategy, key=lambda s: s.priority)
        return (last_step.engine, last_step.use_proxy)

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "mode": self.mode.value,
            "crawler_engine": self.crawler_engine.value,
            "asset_types": [at.value for at in self.asset_types],
            "retry_strategy": [step.to_dict() for step in self.retry_strategy],
            "use_proxy": self.use_proxy,
            "proxy_config": self.proxy_config.to_dict() if self.proxy_config else None,
            "max_depth": self.max_depth,
            "follow_external_links": self.follow_external_links,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlerConfig":
        """
        Create CrawlerConfig from dictionary.

        Args:
            data: Dictionary with crawler config keys

        Returns:
            CrawlerConfig instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        if not isinstance(data, dict):
            raise ValueError("Input must be a dictionary")

        # Parse required fields
        mode = CrawlerMode(data["mode"])
        crawler_engine = CrawlerEngine(data["crawler_engine"])

        # Parse asset types
        asset_types = [AssetType(at) for at in data.get("asset_types", [])]

        # Parse retry strategy
        retry_strategy = [
            RetryStep.from_dict(step)
            for step in data.get("retry_strategy", [])
        ]

        # Parse proxy config
        proxy_config = None
        if data.get("proxy_config"):
            proxy_config = ProxyConfig.from_dict(data["proxy_config"])

        return cls(
            mode=mode,
            crawler_engine=crawler_engine,
            asset_types=asset_types,
            retry_strategy=retry_strategy,
            use_proxy=data.get("use_proxy", False),
            proxy_config=proxy_config,
            max_depth=data.get("max_depth", 3),
            follow_external_links=data.get("follow_external_links", False),
        )

    @classmethod
    def default(cls) -> "CrawlerConfig":
        """
        Create default configuration.

        Returns:
            CrawlerConfig with sensible defaults:
            - Page only mode (no assets)
            - BeautifulSoup engine
            - No proxy
            - No retry strategy
        """
        return cls(
            mode=CrawlerMode.PAGE_ONLY,
            crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
        )

    @classmethod
    def with_retry(
        cls,
        mode: CrawlerMode = CrawlerMode.PAGE_ONLY,
        proxy_config: Optional[ProxyConfig] = None
    ) -> "CrawlerConfig":
        """
        Create configuration with default retry strategy.

        Default retry strategy:
        1. BeautifulSoup without proxy
        2. BeautifulSoup with proxy (if proxy_config provided)
        3. Playwright without proxy
        4. Playwright with proxy (if proxy_config provided)

        Args:
            mode: Crawler mode
            proxy_config: Optional proxy configuration

        Returns:
            CrawlerConfig with retry strategy
        """
        retry_strategy = [
            RetryStep(priority=1, engine=CrawlerEngine.BEAUTIFULSOUP, use_proxy=False),
        ]

        if proxy_config:
            retry_strategy.extend([
                RetryStep(priority=2, engine=CrawlerEngine.BEAUTIFULSOUP, use_proxy=True),
                RetryStep(priority=3, engine=CrawlerEngine.PLAYWRIGHT, use_proxy=False),
                RetryStep(priority=4, engine=CrawlerEngine.PLAYWRIGHT, use_proxy=True),
            ])
        else:
            retry_strategy.append(
                RetryStep(priority=2, engine=CrawlerEngine.PLAYWRIGHT, use_proxy=False)
            )

        return cls(
            mode=mode,
            crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
            retry_strategy=retry_strategy,
            use_proxy=proxy_config is not None,  # Set to True if proxy_config provided
            proxy_config=proxy_config,
        )
