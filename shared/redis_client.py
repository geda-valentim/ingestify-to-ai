import redis
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from shared.config import get_settings


class RedisClient:
    def __init__(self, client=None):
        """
        Initialize Redis client

        Args:
            client: Optional Redis client instance (for testing). If None, creates production client.
        """
        settings = get_settings()

        if client is not None:
            # Use provided client (for testing)
            self.client = client
        else:
            # Create production Redis client
            self.client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True,
            )

        self.result_ttl = settings.result_ttl_seconds

    def ping(self) -> bool:
        """Check Redis connection"""
        try:
            return self.client.ping()
        except Exception:
            return False

    def set_job_status(
        self,
        job_id: str,
        job_type: str,
        status: str,
        progress: int = 0,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        parent_job_id: Optional[str] = None,
        page_number: Optional[int] = None,
        child_job_ids: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> bool:
        """Set job status in Redis"""
        key = f"job:{job_id}:status"
        data = {
            "type": job_type,
            "status": status,
            "progress": progress,
            "error": error,
        }
        if started_at:
            data["started_at"] = started_at.isoformat()
        if completed_at:
            data["completed_at"] = completed_at.isoformat()
        if parent_job_id:
            data["parent_job_id"] = parent_job_id
        if page_number is not None:
            data["page_number"] = page_number
        if child_job_ids:
            data["child_job_ids"] = child_job_ids
        if name:
            data["name"] = name

        try:
            self.client.set(key, json.dumps(data), ex=86400)  # 24h TTL
            return True
        except Exception as e:
            print(f"Error setting job status: {e}")
            return False

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status from Redis"""
        key = f"job:{job_id}:status"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            print(f"Error getting job status: {e}")
            return None

    def update_job_progress(self, job_id: str, progress: int) -> bool:
        """Update job progress"""
        status_data = self.get_job_status(job_id)
        if status_data:
            status_data["progress"] = progress
            key = f"job:{job_id}:status"
            try:
                self.client.set(key, json.dumps(status_data), ex=86400)
                return True
            except Exception as e:
                print(f"Error updating progress: {e}")
                return False
        return False

    def set_job_result(self, job_id: str, result: Dict[str, Any]) -> bool:
        """Store job result in Redis with TTL"""
        key = f"job:{job_id}:result"
        try:
            self.client.set(key, json.dumps(result), ex=self.result_ttl)
            return True
        except Exception as e:
            print(f"Error setting job result: {e}")
            return False

    def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job result from Redis"""
        key = f"job:{job_id}:result"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            print(f"Error getting job result: {e}")
            return None

    def delete_job(self, job_id: str) -> bool:
        """Delete job data from Redis"""
        try:
            self.client.delete(f"job:{job_id}:status", f"job:{job_id}:result")
            return True
        except Exception as e:
            print(f"Error deleting job: {e}")
            return False

    def close(self):
        """Close Redis connection"""
        self.client.close()

    # ============================================
    # Page-level methods (para PDFs divididos)
    # ============================================

    def set_job_pages(self, job_id: str, total_pages: int) -> bool:
        """Define número total de páginas do job"""
        key = f"job:{job_id}:pages:total"
        try:
            self.client.set(key, total_pages, ex=86400)
            return True
        except Exception as e:
            print(f"Error setting total pages: {e}")
            return False

    def get_job_pages_total(self, job_id: str) -> Optional[int]:
        """Retorna número total de páginas"""
        key = f"job:{job_id}:pages:total"
        try:
            total = self.client.get(key)
            return int(total) if total else None
        except Exception as e:
            print(f"Error getting total pages: {e}")
            return None

    def set_page_status(
        self,
        job_id: str,
        page_number: int,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Define status de uma página específica"""
        key = f"job:{job_id}:page:{page_number}"
        data = {
            "page_number": page_number,
            "status": status,
            "error": error,
        }
        if started_at:
            data["started_at"] = started_at.isoformat()
        if completed_at:
            data["completed_at"] = completed_at.isoformat()

        try:
            self.client.set(key, json.dumps(data), ex=86400)
            return True
        except Exception as e:
            print(f"Error setting page status: {e}")
            return False

    def get_page_status(self, job_id: str, page_number: int) -> Optional[Dict[str, Any]]:
        """Retorna status de uma página específica"""
        key = f"job:{job_id}:page:{page_number}"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            print(f"Error getting page status: {e}")
            return None

    def get_all_pages_status(self, job_id: str) -> Dict[int, Dict[str, Any]]:
        """Retorna status de todas as páginas do job"""
        total_pages = self.get_job_pages_total(job_id)
        if not total_pages:
            return {}

        pages_status = {}
        for page_num in range(1, total_pages + 1):
            status = self.get_page_status(job_id, page_num)
            if status:
                pages_status[page_num] = status

        return pages_status

    def set_page_result(self, job_id: str, page_number: int, markdown: str) -> bool:
        """Armazena resultado de uma página"""
        key = f"job:{job_id}:page:{page_number}:result"
        try:
            self.client.set(key, markdown, ex=self.result_ttl)
            return True
        except Exception as e:
            print(f"Error setting page result: {e}")
            return False

    def get_page_result(self, job_id: str, page_number: int) -> Optional[str]:
        """Retorna markdown de uma página"""
        key = f"job:{job_id}:page:{page_number}:result"
        try:
            return self.client.get(key)
        except Exception as e:
            print(f"Error getting page result: {e}")
            return None

    def get_all_pages_results(self, job_id: str) -> Dict[int, str]:
        """Retorna markdown de todas as páginas ordenadas"""
        total_pages = self.get_job_pages_total(job_id)
        if not total_pages:
            return {}

        results = {}
        for page_num in range(1, total_pages + 1):
            markdown = self.get_page_result(job_id, page_num)
            if markdown:
                results[page_num] = markdown

        return results

    def calculate_job_progress(self, job_id: str) -> int:
        """Calcula progresso baseado em páginas completadas"""
        total_pages = self.get_job_pages_total(job_id)
        if not total_pages:
            return 0

        pages_status = self.get_all_pages_status(job_id)
        completed = sum(1 for p in pages_status.values() if p.get("status") == "completed")

        return int((completed / total_pages) * 100)

    # ============================================
    # Hierarquia de Jobs (parent/child)
    # ============================================

    def add_child_job(self, parent_job_id: str, child_type: str, child_job_id: str) -> bool:
        """Adiciona child job ao parent"""
        parent_status = self.get_job_status(parent_job_id)
        if not parent_status:
            return False

        child_jobs = parent_status.get("child_job_ids", {})

        if child_type == "split":
            child_jobs["split_job_id"] = child_job_id
        elif child_type == "page":
            if "page_job_ids" not in child_jobs:
                child_jobs["page_job_ids"] = []
            child_jobs["page_job_ids"].append(child_job_id)
        elif child_type == "merge":
            child_jobs["merge_job_id"] = child_job_id

        # Update parent with child jobs
        parent_status["child_job_ids"] = child_jobs

        try:
            key = f"job:{parent_job_id}:status"
            self.client.set(key, json.dumps(parent_status), ex=86400)
            return True
        except Exception as e:
            print(f"Error adding child job: {e}")
            return False

    def get_child_jobs(self, parent_job_id: str) -> Optional[Dict[str, Any]]:
        """Retorna child jobs do parent"""
        parent_status = self.get_job_status(parent_job_id)
        if parent_status:
            return parent_status.get("child_job_ids")
        return None

    def get_page_jobs(self, parent_job_id: str) -> List[str]:
        """Retorna lista de page job IDs"""
        child_jobs = self.get_child_jobs(parent_job_id)
        if child_jobs and "page_job_ids" in child_jobs:
            return child_jobs["page_job_ids"]
        return []

    def get_page_job_id_by_number(self, parent_job_id: str, page_number: int) -> Optional[str]:
        """
        Busca o job_id de uma página específica pelo número da página

        Args:
            parent_job_id: ID do job principal
            page_number: Número da página (1-based)

        Returns:
            job_id da página ou None se não encontrada
        """
        page_job_ids = self.get_page_jobs(parent_job_id)

        for page_job_id in page_job_ids:
            page_status = self.get_job_status(page_job_id)
            if page_status and page_status.get("page_number") == page_number:
                return page_job_id

        return None

    def count_completed_page_jobs(self, parent_job_id: str) -> int:
        """Conta quantos page jobs estão completed"""
        page_job_ids = self.get_page_jobs(parent_job_id)
        completed = 0

        for page_job_id in page_job_ids:
            status = self.get_job_status(page_job_id)
            if status and status.get("status") == "completed":
                completed += 1

        return completed

    def count_failed_page_jobs(self, parent_job_id: str) -> int:
        """Conta quantos page jobs falharam"""
        page_job_ids = self.get_page_jobs(parent_job_id)
        failed = 0

        for page_job_id in page_job_ids:
            status = self.get_job_status(page_job_id)
            if status and status.get("status") == "failed":
                failed += 1

        return failed

    def all_page_jobs_completed(self, parent_job_id: str) -> bool:
        """Verifica se todos page jobs estão completed"""
        page_job_ids = self.get_page_jobs(parent_job_id)
        if not page_job_ids:
            return False

        for page_job_id in page_job_ids:
            status = self.get_job_status(page_job_id)
            if not status or status.get("status") != "completed":
                return False

        return True


# Global instance
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """Get or create Redis client instance"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
