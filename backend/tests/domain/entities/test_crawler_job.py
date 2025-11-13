"""
Tests for CrawlerJob entity
"""
import pytest
from datetime import datetime, timezone
from domain.entities.crawler_job import CrawlerJob
from domain.entities.job import JobType, JobStatus
from domain.value_objects.crawler_config import CrawlerConfig
from domain.value_objects.crawler_schedule import CrawlerSchedule
from domain.value_objects.crawler_enums import CrawlerMode, CrawlerEngine, ScheduleType


def test_crawler_job_creation():
    """Test creating a basic crawler job"""
    config = CrawlerConfig(
        mode=CrawlerMode.PAGE_ONLY,
        crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
    )
    schedule = CrawlerSchedule(
        type=ScheduleType.ONE_TIME,
        timezone="UTC",
    )

    job = CrawlerJob(
        id="test-crawler-1",
        user_id="user-123",
        job_type=JobType.CRAWLER,
        status=JobStatus.PENDING,
        source_url="https://example.com",
        crawler_config=config,
        crawler_schedule=schedule,
    )

    assert job.id == "test-crawler-1"
    assert job.user_id == "user-123"
    assert job.job_type == JobType.CRAWLER
    assert job.source_url == "https://example.com"
    assert job.crawler_config == config
    assert job.crawler_schedule == schedule


def test_crawler_job_forces_crawler_type():
    """Test that CrawlerJob forces job_type to CRAWLER"""
    config = CrawlerConfig.default()
    schedule = CrawlerSchedule.one_time()

    job = CrawlerJob(
        id="test-1",
        user_id="user-1",
        job_type=JobType.MAIN,  # Try to set wrong type
        status=JobStatus.PENDING,
        source_url="https://example.com",
        crawler_config=config,
        crawler_schedule=schedule,
    )

    # Should be forced to CRAWLER
    assert job.job_type == JobType.CRAWLER


def test_crawler_job_rejects_localhost():
    """Test that localhost URLs are rejected"""
    config = CrawlerConfig.default()
    schedule = CrawlerSchedule.one_time()

    with pytest.raises(ValueError, match="localhost or private IP"):
        CrawlerJob(
            id="test-1",
            user_id="user-1",
            job_type=JobType.CRAWLER,
            status=JobStatus.PENDING,
            source_url="http://localhost:8080",
            crawler_config=config,
            crawler_schedule=schedule,
        )


def test_crawler_job_rejects_private_ip():
    """Test that private IPs are rejected"""
    config = CrawlerConfig.default()
    schedule = CrawlerSchedule.one_time()

    with pytest.raises(ValueError, match="localhost or private IP"):
        CrawlerJob(
            id="test-1",
            user_id="user-1",
            job_type=JobType.CRAWLER,
            status=JobStatus.PENDING,
            source_url="http://192.168.1.1",
            crawler_config=config,
            crawler_schedule=schedule,
        )


def test_crawler_job_requires_config():
    """Test that crawler_config is required"""
    schedule = CrawlerSchedule.one_time()

    with pytest.raises(ValueError, match="must have crawler_config"):
        CrawlerJob(
            id="test-1",
            user_id="user-1",
            job_type=JobType.CRAWLER,
            status=JobStatus.PENDING,
            source_url="https://example.com",
            crawler_config=None,
            crawler_schedule=schedule,
        )


def test_crawler_job_requires_schedule():
    """Test that crawler_schedule is required"""
    config = CrawlerConfig.default()

    with pytest.raises(ValueError, match="must have crawler_schedule"):
        CrawlerJob(
            id="test-1",
            user_id="user-1",
            job_type=JobType.CRAWLER,
            status=JobStatus.PENDING,
            source_url="https://example.com",
            crawler_config=config,
            crawler_schedule=None,
        )


def test_crawler_job_activate():
    """Test activating a crawler"""
    config = CrawlerConfig.default()
    schedule = CrawlerSchedule.one_time()

    job = CrawlerJob(
        id="test-1",
        user_id="user-1",
        job_type=JobType.CRAWLER,
        status=JobStatus.PENDING,
        source_url="https://example.com",
        crawler_config=config,
        crawler_schedule=schedule,
    )

    job.activate()

    assert job.status == JobStatus.QUEUED
    assert job.is_active()


def test_crawler_job_pause():
    """Test pausing a crawler"""
    config = CrawlerConfig.default()
    schedule = CrawlerSchedule.one_time()

    job = CrawlerJob(
        id="test-1",
        user_id="user-1",
        job_type=JobType.CRAWLER,
        status=JobStatus.QUEUED,
        source_url="https://example.com",
        crawler_config=config,
        crawler_schedule=schedule,
    )

    job.pause()

    assert job.status == JobStatus.CANCELLED
    assert job.is_paused()
    assert not job.is_active()


def test_crawler_job_stop():
    """Test stopping a crawler permanently"""
    config = CrawlerConfig.default()
    schedule = CrawlerSchedule.one_time()

    job = CrawlerJob(
        id="test-1",
        user_id="user-1",
        job_type=JobType.CRAWLER,
        status=JobStatus.QUEUED,
        source_url="https://example.com",
        crawler_config=config,
        crawler_schedule=schedule,
    )

    job.stop()

    assert job.status == JobStatus.CANCELLED
    assert job.completed_at is not None
    assert job.is_stopped()


def test_crawler_job_get_normalized_url():
    """Test getting normalized URL"""
    config = CrawlerConfig.default()
    schedule = CrawlerSchedule.one_time()

    job = CrawlerJob(
        id="test-1",
        user_id="user-1",
        job_type=JobType.CRAWLER,
        status=JobStatus.PENDING,
        source_url="HTTPS://Example.COM/Path?b=2&a=1",
        crawler_config=config,
        crawler_schedule=schedule,
    )

    normalized = job.get_normalized_url()
    assert normalized == "https://example.com/Path?a=1&b=2"


def test_crawler_job_get_url_pattern():
    """Test getting URL pattern for duplicate detection"""
    config = CrawlerConfig.default()
    schedule = CrawlerSchedule.one_time()

    job = CrawlerJob(
        id="test-1",
        user_id="user-1",
        job_type=JobType.CRAWLER,
        status=JobStatus.PENDING,
        source_url="https://example.com/page?id=123&sort=desc",
        crawler_config=config,
        crawler_schedule=schedule,
    )

    pattern = job.get_url_pattern()
    assert pattern == "https://example.com/page?id=*&sort=*"
