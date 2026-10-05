"""
Shared pytest configuration.

These are unit tests: they must run without Redis, MySQL, Elasticsearch or MinIO.
Anything that needs a live service belongs in an integration test, not here.
"""

import os
import sys
from pathlib import Path

# `backend/` is the import root - modules import as `shared.*`, `api.*`, `workers.*`.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Settings are required (and validated) at import time, so they must be present
# before any module that calls get_settings() is imported. These values are
# test-only and must never resemble a real credential.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-any-real-environment-0123456789abcdef")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret-key")

# Keep the suite free of torch, transformers and any model download: the stub
# provider is a real ImageDescriber with deterministic output and no heavy
# imports. Tests that need the Florence-2 code path build it directly and inject
# a fake backend.
os.environ.setdefault("VISION_PROVIDER", "stub")

import pytest  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402


@pytest.fixture
def fake_redis():
    """An in-memory Redis, wired through the real RedisClient."""
    import fakeredis
    from shared.redis_client import RedisClient

    return RedisClient(client=fakeredis.FakeRedis(decode_responses=True))



@pytest.fixture
def mock_datetime():
    """Fixture for mocking datetime."""
    return datetime(2025, 1, 13, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_user_id():
    """Fixture for test user ID."""
    return "test-user-123"


@pytest.fixture
def sample_job_id():
    """Fixture for test job ID."""
    return "test-job-456"


@pytest.fixture
def sample_crawler_url():
    """Fixture for test crawler URL."""
    return "https://example.com/page"


@pytest.fixture
def mock_db_session():
    """Fixture for mocking database session."""
    session = MagicMock()
    session.query = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.close = MagicMock()
    return session
