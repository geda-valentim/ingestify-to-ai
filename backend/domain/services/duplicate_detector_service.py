"""
Duplicate Detector Service - Domain logic for detecting duplicate files

Detects duplicate files during crawler execution based on URL hash.
Used to skip already downloaded files and avoid wasting resources.
"""
import hashlib
from typing import List, Optional
from domain.entities.crawled_file import CrawledFile
from domain.services.url_normalizer_service import URLNormalizerService


class DuplicateDetectorService:
    """
    Domain service for detecting duplicate files during crawling.

    Uses URL normalization and hashing to identify files that have
    already been downloaded, even if URLs differ slightly.

    Business rules:
    - Duplicate detection based on normalized URL hash
    - Case-insensitive comparison
    - Query parameter order doesn't matter
    - Same file at different URLs = different files (intentional)
    """

    @staticmethod
    def generate_file_hash(url: str) -> str:
        """
        Generate hash from normalized URL for duplicate detection.

        Args:
            url: File URL to hash

        Returns:
            SHA256 hash of normalized URL (hex string)

        Raises:
            ValueError: If URL is invalid

        Example:
            >>> generate_file_hash("https://example.com/file.pdf?v=1")
            'a1b2c3d4...'
        """
        # Normalize URL first (removes trailing slashes, sorts params, etc.)
        normalized_url = URLNormalizerService.normalize_url(url)

        # Generate SHA256 hash
        hash_obj = hashlib.sha256(normalized_url.encode('utf-8'))
        return hash_obj.hexdigest()

    @staticmethod
    def is_duplicate(url: str, existing_files: List[CrawledFile]) -> bool:
        """
        Check if file URL already exists in list of files.

        Args:
            url: URL to check
            existing_files: List of already crawled files

        Returns:
            True if URL is duplicate (already in list)

        Example:
            >>> files = [CrawledFile(url="https://example.com/file.pdf", ...)]
            >>> is_duplicate("https://example.com/file.pdf", files)
            True
        """
        try:
            url_hash = DuplicateDetectorService.generate_file_hash(url)

            for file in existing_files:
                try:
                    existing_hash = DuplicateDetectorService.generate_file_hash(file.url)
                    if url_hash == existing_hash:
                        return True
                except ValueError:
                    # Skip invalid URLs in existing files
                    continue

            return False

        except ValueError:
            # Invalid URL - consider as duplicate to prevent download
            return True

    @staticmethod
    def find_duplicate(url: str, existing_files: List[CrawledFile]) -> Optional[CrawledFile]:
        """
        Find duplicate file in list.

        Args:
            url: URL to search for
            existing_files: List of already crawled files

        Returns:
            CrawledFile if duplicate found, None otherwise

        Example:
            >>> files = [CrawledFile(url="https://example.com/file.pdf", ...)]
            >>> duplicate = find_duplicate("https://example.com/file.pdf", files)
            >>> duplicate.url
            'https://example.com/file.pdf'
        """
        try:
            url_hash = DuplicateDetectorService.generate_file_hash(url)

            for file in existing_files:
                try:
                    existing_hash = DuplicateDetectorService.generate_file_hash(file.url)
                    if url_hash == existing_hash:
                        return file
                except ValueError:
                    # Skip invalid URLs
                    continue

            return None

        except ValueError:
            return None

    @staticmethod
    def filter_duplicates(urls: List[str]) -> List[str]:
        """
        Remove duplicate URLs from list (keeps first occurrence).

        Args:
            urls: List of URLs to deduplicate

        Returns:
            List of unique URLs

        Example:
            >>> urls = [
            ...     "https://example.com/file.pdf",
            ...     "https://example.com/file.pdf?v=1",  # Different params
            ...     "https://example.com/file.pdf",       # Exact duplicate
            ... ]
            >>> filter_duplicates(urls)
            ['https://example.com/file.pdf', 'https://example.com/file.pdf?v=1']
        """
        seen_hashes = set()
        unique_urls = []

        for url in urls:
            try:
                url_hash = DuplicateDetectorService.generate_file_hash(url)

                if url_hash not in seen_hashes:
                    seen_hashes.add(url_hash)
                    unique_urls.append(url)

            except ValueError:
                # Skip invalid URLs
                continue

        return unique_urls

    @staticmethod
    def count_duplicates(urls: List[str]) -> int:
        """
        Count number of duplicate URLs in list.

        Args:
            urls: List of URLs

        Returns:
            Number of duplicates found

        Example:
            >>> urls = ["https://example.com/a", "https://example.com/a", "https://example.com/b"]
            >>> count_duplicates(urls)
            1
        """
        total = len(urls)
        unique = len(DuplicateDetectorService.filter_duplicates(urls))
        return total - unique

    @staticmethod
    def group_by_hash(urls: List[str]) -> dict[str, List[str]]:
        """
        Group URLs by their hash (identifies duplicates).

        Args:
            urls: List of URLs to group

        Returns:
            Dict mapping hash -> list of URLs with that hash

        Example:
            >>> urls = [
            ...     "https://example.com/file.pdf",
            ...     "https://example.com/file.pdf",
            ...     "https://example.com/other.pdf",
            ... ]
            >>> groups = group_by_hash(urls)
            >>> len(groups)
            2
            >>> len(groups[hash1])  # First hash has 2 URLs
            2
        """
        groups = {}

        for url in urls:
            try:
                url_hash = DuplicateDetectorService.generate_file_hash(url)

                if url_hash not in groups:
                    groups[url_hash] = []

                groups[url_hash].append(url)

            except ValueError:
                # Skip invalid URLs
                continue

        return groups

    @staticmethod
    def are_files_duplicate(file1: CrawledFile, file2: CrawledFile) -> bool:
        """
        Check if two CrawledFile entities are duplicates.

        Args:
            file1: First file
            file2: Second file

        Returns:
            True if files have same URL hash

        Example:
            >>> file1 = CrawledFile(url="https://example.com/file.pdf", ...)
            >>> file2 = CrawledFile(url="https://example.com/file.pdf", ...)
            >>> are_files_duplicate(file1, file2)
            True
        """
        try:
            hash1 = DuplicateDetectorService.generate_file_hash(file1.url)
            hash2 = DuplicateDetectorService.generate_file_hash(file2.url)
            return hash1 == hash2
        except ValueError:
            return False

    @staticmethod
    def get_duplicate_stats(files: List[CrawledFile]) -> dict:
        """
        Get statistics about duplicates in file list.

        Args:
            files: List of crawled files

        Returns:
            Dict with statistics:
            - total: Total files
            - unique: Unique files (by URL hash)
            - duplicates: Number of duplicates
            - duplicate_groups: Number of unique file groups

        Example:
            >>> stats = get_duplicate_stats(files)
            >>> stats
            {
                'total': 100,
                'unique': 85,
                'duplicates': 15,
                'duplicate_groups': 5
            }
        """
        if not files:
            return {
                'total': 0,
                'unique': 0,
                'duplicates': 0,
                'duplicate_groups': 0
            }

        total = len(files)
        urls = [f.url for f in files]

        # Group by hash
        groups = DuplicateDetectorService.group_by_hash(urls)

        # Count groups with more than 1 URL
        duplicate_groups = sum(1 for urls in groups.values() if len(urls) > 1)

        unique = len(groups)
        duplicates = total - unique

        return {
            'total': total,
            'unique': unique,
            'duplicates': duplicates,
            'duplicate_groups': duplicate_groups
        }
