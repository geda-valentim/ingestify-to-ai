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

        # Create indices if not exist
        if not self.client.indices.exists(index="job_results"):
            self.client.indices.create(index="job_results", body=job_results_mapping)

        if not self.client.indices.exists(index="page_results"):
            self.client.indices.create(index="page_results", body=page_results_mapping)

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
