from elasticsearch import Elasticsearch, NotFoundError
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from shared.config import get_settings

settings = get_settings()


class ElasticsearchClient:
    """Client for Elasticsearch operations - stores document content"""

    def __init__(self):
        self.client = Elasticsearch(
            [settings.elasticsearch_url],
            basic_auth=(settings.elasticsearch_user, settings.elasticsearch_password)
                if settings.elasticsearch_user else None,
            verify_certs=settings.elasticsearch_verify_certs,
        )
        self._create_indices()

    def _create_indices(self):
        """Create indices if they don't exist"""
        # Index for full job results (merged markdown)
        job_results_mapping = {
            "mappings": {
                "properties": {
                    "job_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "markdown_content": {"type": "text"},
                    "filename": {"type": "text"},
                    "total_pages": {"type": "integer"},
                    "char_count": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "metadata": {"type": "object", "enabled": False}
                }
            }
        }

        # Index for individual page results
        page_results_mapping = {
            "mappings": {
                "properties": {
                    "job_id": {"type": "keyword"},
                    "page_number": {"type": "integer"},
                    "markdown_content": {"type": "text"},
                    "char_count": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "metadata": {"type": "object", "enabled": False}
                }
            }
        }

        # Index for crawler jobs (view/projection for fuzzy URL search)
        crawler_jobs_mapping = {
            "mappings": {
                "properties": {
                    "job_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "source_url": {"type": "text"},
                    "normalized_url": {"type": "keyword"},
                    "url_pattern": {"type": "keyword"},
                    "domain": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "crawler_mode": {"type": "keyword"},
                    "crawler_engine": {"type": "keyword"},
                    "schedule_type": {"type": "keyword"},
                    "cron_expression": {"type": "keyword"},
                    "next_run": {"type": "date"},
                    "last_execution": {"type": "date"},
                    "total_executions": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "metadata": {"type": "object", "enabled": False}
                }
            }
        }

        # Create indices if not exist
        if not self.client.indices.exists(index="job_results"):
            self.client.indices.create(index="job_results", body=job_results_mapping)

        if not self.client.indices.exists(index="page_results"):
            self.client.indices.create(index="page_results", body=page_results_mapping)

        if not self.client.indices.exists(index="crawler_jobs"):
            self.client.indices.create(index="crawler_jobs", body=crawler_jobs_mapping)

    # ========== Job Results ==========

    def store_job_result(
        self,
        job_id: str,
        markdown_content: str,
        user_id: Optional[str] = None,
        filename: Optional[str] = None,
        total_pages: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store complete job result (merged markdown) in Elasticsearch

        Args:
            job_id: Unique job identifier
            markdown_content: Full converted markdown
            user_id: User who created the job
            filename: Original filename
            total_pages: Number of pages (for PDFs)
            metadata: Additional metadata
        """
        try:
            doc = {
                "job_id": job_id,
                "user_id": user_id,
                "markdown_content": markdown_content,
                "filename": filename,
                "total_pages": total_pages,
                "char_count": len(markdown_content),
                "created_at": datetime.utcnow(),
                "metadata": metadata or {}
            }

            self.client.index(
                index="job_results",
                id=job_id,
                document=doc
            )
            return True
        except Exception as e:
            print(f"Error storing job result in ES: {e}")
            return False

    def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full job result from Elasticsearch"""
        try:
            response = self.client.get(index="job_results", id=job_id)
            return response["_source"]
        except NotFoundError:
            return None
        except Exception as e:
            print(f"Error getting job result from ES: {e}")
            return None

    def delete_job_result(self, job_id: str) -> bool:
        """Delete job result from Elasticsearch"""
        try:
            self.client.delete(index="job_results", id=job_id)
            return True
        except NotFoundError:
            return True  # Already deleted
        except Exception as e:
            print(f"Error deleting job result from ES: {e}")
            return False

    # ========== Page Results ==========

    def store_page_result(
        self,
        job_id: str,
        page_number: int,
        markdown_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store individual page result in Elasticsearch

        Args:
            job_id: Parent job ID
            page_number: Page number (1-indexed)
            markdown_content: Converted markdown for this page
            metadata: Additional metadata
        """
        try:
            doc_id = f"{job_id}_page_{page_number}"
            doc = {
                "job_id": job_id,
                "page_number": page_number,
                "markdown_content": markdown_content,
                "char_count": len(markdown_content),
                "created_at": datetime.utcnow(),
                "metadata": metadata or {}
            }

            self.client.index(
                index="page_results",
                id=doc_id,
                document=doc
            )
            return True
        except Exception as e:
            print(f"Error storing page result in ES: {e}")
            return False

    def get_page_result(self, job_id: str, page_number: int) -> Optional[Dict[str, Any]]:
        """Retrieve individual page result from Elasticsearch"""
        try:
            doc_id = f"{job_id}_page_{page_number}"
            response = self.client.get(index="page_results", id=doc_id)
            return response["_source"]
        except NotFoundError:
            return None
        except Exception as e:
            print(f"Error getting page result from ES: {e}")
            return None

    def get_all_page_results(self, job_id: str) -> List[Dict[str, Any]]:
        """Retrieve all page results for a job, sorted by page_number"""
        try:
            query = {
                "query": {"term": {"job_id": job_id}},
                "sort": [{"page_number": "asc"}],
                "size": 10000  # Max pages per document
            }

            response = self.client.search(index="page_results", body=query)
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            print(f"Error getting all page results from ES: {e}")
            return []

    def delete_page_result(self, job_id: str, page_number: int) -> bool:
        """Delete individual page result from Elasticsearch"""
        try:
            doc_id = f"{job_id}_page_{page_number}"
            self.client.delete(index="page_results", id=doc_id)
            return True
        except NotFoundError:
            return True  # Already deleted
        except Exception as e:
            print(f"Error deleting page result from ES: {e}")
            return False

    def delete_all_page_results(self, job_id: str) -> bool:
        """Delete all page results for a job"""
        try:
            query = {"query": {"term": {"job_id": job_id}}}
            self.client.delete_by_query(index="page_results", body=query)
            return True
        except Exception as e:
            print(f"Error deleting all page results from ES: {e}")
            return False

    # ========== Search ==========

    def search_jobs(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search job results by content

        Args:
            query: Search query string
            user_id: Filter by user (optional)
            limit: Max results to return
        """
        try:
            must_clauses = [
                {"match": {"markdown_content": query}}
            ]

            if user_id:
                must_clauses.append({"term": {"user_id": user_id}})

            search_query = {
                "query": {"bool": {"must": must_clauses}},
                "size": limit,
                "sort": [{"created_at": "desc"}]
            }

            response = self.client.search(index="job_results", body=search_query)
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            print(f"Error searching jobs in ES: {e}")
            return []

    def search_pages(
        self,
        query: str,
        job_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search page results by content

        Args:
            query: Search query string
            job_id: Filter by job (optional)
            limit: Max results to return
        """
        try:
            must_clauses = [
                {"match": {"markdown_content": query}}
            ]

            if job_id:
                must_clauses.append({"term": {"job_id": job_id}})

            search_query = {
                "query": {"bool": {"must": must_clauses}},
                "size": limit,
                "sort": [{"created_at": "desc"}]
            }

            response = self.client.search(index="page_results", body=search_query)
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            print(f"Error searching pages in ES: {e}")
            return []

    # ========== Crawler Jobs ==========

    def store_crawler_job(
        self,
        job_id: str,
        user_id: str,
        source_url: str,
        normalized_url: str,
        url_pattern: str,
        domain: str,
        status: str,
        crawler_mode: str,
        crawler_engine: str,
        schedule_type: Optional[str] = None,
        cron_expression: Optional[str] = None,
        next_run: Optional[datetime] = None,
        last_execution: Optional[datetime] = None,
        total_executions: int = 0,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store crawler job projection in Elasticsearch for fuzzy URL search.

        This is a view/projection of MySQL data to enable:
        - Fast fuzzy URL matching
        - Domain-based searches
        - URL pattern duplicate detection

        Args:
            job_id: Crawler job ID
            user_id: Owner user ID
            source_url: Original URL
            normalized_url: Normalized URL for exact matching
            url_pattern: URL pattern with wildcards for fuzzy matching
            domain: Extracted domain
            status: Job status (active, paused, stopped)
            crawler_mode: Crawler mode (page_only, etc.)
            crawler_engine: Engine (beautifulsoup, playwright)
            schedule_type: one_time or recurring
            cron_expression: Cron expression for recurring jobs
            next_run: Next scheduled execution
            last_execution: Last execution timestamp
            total_executions: Total number of executions
            created_at: Creation timestamp
            updated_at: Update timestamp
            metadata: Additional metadata
        """
        try:
            doc = {
                "job_id": job_id,
                "user_id": user_id,
                "source_url": source_url,
                "normalized_url": normalized_url,
                "url_pattern": url_pattern,
                "domain": domain,
                "status": status,
                "crawler_mode": crawler_mode,
                "crawler_engine": crawler_engine,
                "schedule_type": schedule_type,
                "cron_expression": cron_expression,
                "next_run": next_run,
                "last_execution": last_execution,
                "total_executions": total_executions,
                "created_at": created_at or datetime.utcnow(),
                "updated_at": updated_at or datetime.utcnow(),
                "metadata": metadata or {}
            }

            self.client.index(
                index="crawler_jobs",
                id=job_id,
                document=doc
            )
            return True
        except Exception as e:
            print(f"Error storing crawler job in ES: {e}")
            return False

    def get_crawler_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve crawler job from Elasticsearch"""
        try:
            response = self.client.get(index="crawler_jobs", id=job_id)
            return response["_source"]
        except NotFoundError:
            return None
        except Exception as e:
            print(f"Error getting crawler job from ES: {e}")
            return None

    def update_crawler_job(
        self,
        job_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update crawler job fields in Elasticsearch

        Args:
            job_id: Crawler job ID
            updates: Dictionary of fields to update
        """
        try:
            updates["updated_at"] = datetime.utcnow()
            self.client.update(
                index="crawler_jobs",
                id=job_id,
                body={"doc": updates}
            )
            return True
        except NotFoundError:
            print(f"Crawler job {job_id} not found in ES")
            return False
        except Exception as e:
            print(f"Error updating crawler job in ES: {e}")
            return False

    def delete_crawler_job(self, job_id: str) -> bool:
        """Delete crawler job from Elasticsearch"""
        try:
            self.client.delete(index="crawler_jobs", id=job_id)
            return True
        except NotFoundError:
            return True  # Already deleted
        except Exception as e:
            print(f"Error deleting crawler job from ES: {e}")
            return False

    def search_crawler_jobs_by_url(
        self,
        url_query: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search crawler jobs by URL (fuzzy matching)

        Args:
            url_query: URL or partial URL to search
            user_id: Filter by user (optional)
            limit: Max results
        """
        try:
            must_clauses = [
                {
                    "multi_match": {
                        "query": url_query,
                        "fields": ["source_url", "normalized_url", "domain"],
                        "fuzziness": "AUTO"
                    }
                }
            ]

            if user_id:
                must_clauses.append({"term": {"user_id": user_id}})

            search_query = {
                "query": {"bool": {"must": must_clauses}},
                "size": limit,
                "sort": [{"created_at": "desc"}]
            }

            response = self.client.search(index="crawler_jobs", body=search_query)
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            print(f"Error searching crawler jobs by URL in ES: {e}")
            return []

    def find_similar_crawler_jobs(
        self,
        url_pattern: str,
        user_id: str,
        exclude_job_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find crawler jobs with same URL pattern (duplicate detection)

        Args:
            url_pattern: URL pattern to match
            user_id: User ID to filter by
            exclude_job_id: Exclude this job ID from results
        """
        try:
            must_clauses = [
                {"term": {"url_pattern": url_pattern}},
                {"term": {"user_id": user_id}}
            ]

            if exclude_job_id:
                must_clauses.append({
                    "bool": {"must_not": {"term": {"job_id": exclude_job_id}}}
                })

            search_query = {
                "query": {"bool": {"must": must_clauses}},
                "size": 100
            }

            response = self.client.search(index="crawler_jobs", body=search_query)
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            print(f"Error finding similar crawler jobs in ES: {e}")
            return []

    def find_crawler_jobs_by_domain(
        self,
        domain: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find all crawler jobs for a specific domain

        Args:
            domain: Domain to search for
            user_id: Filter by user (optional)
            limit: Max results
        """
        try:
            must_clauses = [{"term": {"domain": domain}}]

            if user_id:
                must_clauses.append({"term": {"user_id": user_id}})

            search_query = {
                "query": {"bool": {"must": must_clauses}},
                "size": limit,
                "sort": [{"created_at": "desc"}]
            }

            response = self.client.search(index="crawler_jobs", body=search_query)
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            print(f"Error finding crawler jobs by domain in ES: {e}")
            return []

    # ========== Health Check ==========

    def health_check(self) -> bool:
        """Check if Elasticsearch is healthy"""
        try:
            return self.client.ping()
        except Exception:
            return False


# Singleton instance
_es_client: Optional[ElasticsearchClient] = None


def get_es_client() -> ElasticsearchClient:
    """Get singleton Elasticsearch client instance"""
    global _es_client
    if _es_client is None:
        _es_client = ElasticsearchClient()
    return _es_client
