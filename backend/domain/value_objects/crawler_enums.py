"""
Crawler-specific Enums

Defines all enum types used in crawler configuration.
"""
from enum import Enum


class CrawlerMode(str, Enum):
    """
    Defines what content the crawler should download.

    - PAGE_ONLY: Only the main HTML page
    - PAGE_WITH_ALL: Page + all assets (CSS, JS, images, fonts, videos, etc.)
    - PAGE_WITH_FILTERED: Page + selected asset types only
    - FULL_WEBSITE: Crawl entire website (following links up to max_depth)
    """
    PAGE_ONLY = "page_only"
    PAGE_WITH_ALL = "page_with_all"
    PAGE_WITH_FILTERED = "page_with_filtered"
    FULL_WEBSITE = "full_website"


class CrawlerEngine(str, Enum):
    """
    Web scraping engine to use.

    - BEAUTIFULSOUP: Lightweight, fast, HTTP-only (no JavaScript execution)
    - PLAYWRIGHT: Headless browser, handles JavaScript, slower but more robust
    """
    BEAUTIFULSOUP = "beautifulsoup"
    PLAYWRIGHT = "playwright"


class AssetType(str, Enum):
    """
    Types of web assets that can be downloaded.

    Used with CrawlerMode.PAGE_WITH_FILTERED to specify which assets to download.
    """
    CSS = "css"           # Stylesheets (.css)
    JS = "js"             # JavaScript files (.js)
    IMAGES = "images"     # Images (.jpg, .png, .gif, .svg, .webp)
    FONTS = "fonts"       # Font files (.woff, .woff2, .ttf, .otf)
    VIDEOS = "videos"     # Video files (.mp4, .webm, .ogg)
    DOCUMENTS = "documents"  # Documents (.pdf, .doc, .xlsx, etc.)


class ScheduleType(str, Enum):
    """
    Type of crawler scheduling.

    - ONE_TIME: Execute once immediately or at a specific time
    - RECURRING: Execute repeatedly based on cron expression
    """
    ONE_TIME = "one_time"
    RECURRING = "recurring"


# Mapping of AssetType to file extensions
ASSET_TYPE_EXTENSIONS = {
    AssetType.CSS: [".css"],
    AssetType.JS: [".js", ".mjs"],
    AssetType.IMAGES: [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp"],
    AssetType.FONTS: [".woff", ".woff2", ".ttf", ".otf", ".eot"],
    AssetType.VIDEOS: [".mp4", ".webm", ".ogg", ".avi", ".mov"],
    AssetType.DOCUMENTS: [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt"],
}


def get_extensions_for_asset_type(asset_type: AssetType) -> list[str]:
    """
    Get file extensions for a given asset type.

    Args:
        asset_type: The asset type enum

    Returns:
        List of file extensions (with leading dot)

    Example:
        >>> get_extensions_for_asset_type(AssetType.IMAGES)
        ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp']
    """
    return ASSET_TYPE_EXTENSIONS.get(asset_type, [])


def get_all_extensions(asset_types: list[AssetType]) -> list[str]:
    """
    Get all file extensions for a list of asset types.

    Args:
        asset_types: List of asset type enums

    Returns:
        Deduplicated list of file extensions

    Example:
        >>> get_all_extensions([AssetType.CSS, AssetType.JS])
        ['.css', '.js', '.mjs']
    """
    extensions = []
    for asset_type in asset_types:
        extensions.extend(get_extensions_for_asset_type(asset_type))
    return list(set(extensions))  # Remove duplicates
