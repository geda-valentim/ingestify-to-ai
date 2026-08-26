"""
Redis job cache.

CONTRACT — this module is a TTL cache, nothing more.

Every key written here carries an expiry (24h for status/ownership metadata,
``result_ttl_seconds`` for payloads, 30 days for the per-user job index). A miss
is therefore indistinguishable from "never existed", and callers must treat a
``None`` return as "unknown", never as a fact about the domain.

NO AUTHORIZATION DECISION MAY BE DERIVED FROM THIS MODULE.

Ownership lives in the database and is enforced by ``api/deps.py``. Because
cache entries expire, an ownership check answered from here would silently start
returning "no owner" once the TTL lapsed — turning an access-control question
into a cache-liveness question. ``get_job_owner`` survives solely as the
best-effort fallback ``api/deps.py`` consults when the database has no row yet
(freshly enqueued jobs); it is that module's job to decide what an absent owner
means, and its answer is deny.

Do not reintroduce a ``verify_job_ownership``-style helper here.
"""

import redis
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from shared.config import get_settings

logger = logging.getLogger(__name__)

# Single key, shared by every vision worker: the endpoint answers "what can this
# deployment do", not "how many workers are up". Last writer wins, and the
# survivors keep it alive when one of several dies.
#
# Key AND lifetime live together, here, because the writer (the vision worker)
# and the reader (`GET /images/capabilities`) are different processes that must
# not be able to disagree about how long a statement stays true. The worker
# republishes at a third of this; the reader rejects anything older than it.
VISION_HEARTBEAT_KEY = "vision:worker:heartbeat"
VISION_HEARTBEAT_TTL_SECONDS = 45


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
            logger.error("Failed to cache status for job %s: %s", job_id, e)
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
            logger.error("Failed to read cached status for job %s: %s", job_id, e)
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
                logger.error("Failed to update cached progress for job %s: %s", job_id, e)
                return False
        return False

    def set_job_result(self, job_id: str, result: Dict[str, Any]) -> bool:
        """Store job result in Redis with TTL"""
        key = f"job:{job_id}:result"
        try:
            self.client.set(key, json.dumps(result), ex=self.result_ttl)
            return True
        except Exception as e:
            logger.error("Failed to cache result for job %s: %s", job_id, e)
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
            logger.error("Failed to read cached result for job %s: %s", job_id, e)
            return None

    def delete_job(self, job_id: str) -> bool:
        """Delete job data from Redis"""
        try:
            self.client.delete(f"job:{job_id}:status", f"job:{job_id}:result")
            return True
        except Exception as e:
            logger.error("Failed to evict cache entries for job %s: %s", job_id, e)
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
            logger.error("Failed to cache page total for job %s: %s", job_id, e)
            return False

    def get_job_pages_total(self, job_id: str) -> Optional[int]:
        """Retorna número total de páginas"""
        key = f"job:{job_id}:pages:total"
        try:
            total = self.client.get(key)
            return int(total) if total else None
        except Exception as e:
            logger.error("Failed to read cached page total for job %s: %s", job_id, e)
            return None

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
            logger.error(
                "Failed to attach %s child job %s to parent job %s: %s",
                child_type, child_job_id, parent_job_id, e,
            )
            return False

    def get_child_jobs(self, parent_job_id: str) -> Optional[Dict[str, Any]]:
        """Retorna child jobs do parent.

        Internal helper: the only caller is get_page_jobs() below.
        """
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

    # ============================================
    # Vision worker heartbeat
    # ============================================

    def set_vision_heartbeat(self, payload: Dict[str, Any], ttl_seconds: int) -> bool:
        """
        Publish what the calling vision worker can do, under a TTL.

        A TTL is not an optimisation here, it is the whole design: this key is
        the ONLY evidence ``GET /images/capabilities`` has that a vision worker
        exists, and a record without an expiry would keep describing a worker
        that died. The writer republishes well inside ``ttl_seconds``; when it
        stops, the key goes, and absence means "no worker" — which is exactly
        how the endpoint reads it.

        Args:
            payload: The capabilities report, including ``published_at``.
            ttl_seconds: How long this statement stays believable.

        Returns:
            True if written.
        """
        try:
            self.client.set(
                VISION_HEARTBEAT_KEY, json.dumps(payload), ex=int(ttl_seconds)
            )
            return True
        except Exception as e:
            logger.warning("Failed to publish the vision worker heartbeat: %s", e)
            return False

    def get_vision_heartbeat(self) -> Optional[Dict[str, Any]]:
        """
        The most recent vision worker heartbeat, or None.

        None covers three cases the caller must treat identically — no worker
        ever ran, the last one died more than a TTL ago, or the record is
        unreadable — because none of them is evidence that vision works.

        Returns:
            The decoded report, or None.
        """
        try:
            raw = self.client.get(VISION_HEARTBEAT_KEY)
        except Exception as e:
            logger.warning("Failed to read the vision worker heartbeat: %s", e)
            return None

        if not raw:
            return None

        try:
            payload = json.loads(raw)
        except (ValueError, TypeError) as e:
            logger.warning("Vision worker heartbeat is not decodable JSON: %s", e)
            return None

        return payload if isinstance(payload, dict) else None

    # ============================================
    # Job Ownership (User Isolation)
    # ============================================

    def set_job_owner(self, job_id: str, user_id: str) -> bool:
        """
        Set owner of a job

        Args:
            job_id: Job ID
            user_id: User ID (owner)

        Returns:
            True if successful
        """
        key = f"job:{job_id}:owner"
        try:
            self.client.set(key, user_id, ex=86400)  # 24h TTL
            return True
        except Exception as e:
            logger.error("Failed to cache owner for job %s: %s", job_id, e)
            return False

    def get_job_owner(self, job_id: str) -> Optional[str]:
        """
        Get the cached owner of a job.

        NOT an authorization check. This is a best-effort cache lookup whose
        sole consumer is the fallback path in ``api/deps.py``, used when the
        database has no row for the job yet. The entry expires after 24h, so
        None means "unknown", not "unowned" — only ``api/deps.py`` may turn
        this into an allow/deny decision, and absent means deny.

        Args:
            job_id: Job ID

        Returns:
            User ID (owner) or None if unknown/expired
        """
        key = f"job:{job_id}:owner"
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(
                "Failed to read cached owner for job %s; caller must treat this as "
                "unknown and deny: %s",
                job_id, e,
            )
            return None

    def add_job_to_user(self, user_id: str, job_id: str) -> bool:
        """
        Add job to user's job list

        Args:
            user_id: User ID
            job_id: Job ID to add

        Returns:
            True if successful
        """
        key = f"user:{user_id}:jobs"
        try:
            self.client.sadd(key, job_id)
            self.client.expire(key, 86400 * 30)  # 30 days TTL
            return True
        except Exception as e:
            logger.error("Failed to index job %s under user %s: %s", job_id, user_id, e)
            return False

    def get_user_jobs(self, user_id: str, limit: int = 100) -> List[str]:
        """
        Get all job IDs for a user

        Args:
            user_id: User ID
            limit: Maximum number of jobs to return

        Returns:
            List of job IDs
        """
        key = f"user:{user_id}:jobs"
        try:
            # Get all members of the set
            job_ids = self.client.smembers(key)
            # Convert to list and limit
            return list(job_ids)[:limit]
        except Exception as e:
            logger.error("Failed to read job index for user %s: %s", user_id, e)
            return []

    def remove_job_from_user(self, user_id: str, job_id: str) -> bool:
        """
        Remove job from user's job list

        Args:
            user_id: User ID
            job_id: Job ID to remove

        Returns:
            True if successful
        """
        key = f"user:{user_id}:jobs"
        try:
            self.client.srem(key, job_id)
            return True
        except Exception as e:
            logger.error("Failed to unindex job %s from user %s: %s", job_id, user_id, e)
            return False


# Global instance
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """Get or create Redis client instance"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
