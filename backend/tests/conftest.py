"""Shared test fixtures for pytest."""
import pytest
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock


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
