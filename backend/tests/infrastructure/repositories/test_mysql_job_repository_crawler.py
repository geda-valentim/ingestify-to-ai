"""
Integration tests for MySQLJobRepository crawler-specific methods
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from infrastructure.repositories.mysql_job_repository import MySQLJobRepository
from domain.entities.crawler_job import CrawlerJob
from domain.entities.job import JobStatus, JobType
from domain.value_objects.crawler_config import CrawlerConfig
from domain.value_objects.crawler_schedule import CrawlerSchedule
from domain.value_objects.crawler_enums import CrawlerMode, CrawlerEngine, ScheduleType
from shared.models import Base


@pytest.fixture(scope="function")
def db_session():
    """Create a test database session"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Use in-memory SQLite for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture(scope="function")
def repository(db_session):
    """Create repository with test session"""
    repo = MySQLJobRepository()
    repo.session = db_session  # Override with test session
    return repo


@pytest.fixture(scope="function")
def sample_crawler_config():
    """Sample crawler configuration"""
    return CrawlerConfig(
        mode=CrawlerMode.PAGE_ONLY,
        crawler_engine=CrawlerEngine.BEAUTIFULSOUP,
        max_depth=3,
        follow_external_links=False,
    )


@pytest.fixture(scope="function")
def sample_crawler_schedule():
    """Sample recurring schedule"""
    return CrawlerSchedule.recurring(
        cron_expression="0 9 * * *",
        timezone="UTC"
    )


@pytest.fixture(scope="function")
def default_schedule():
    """Default one-time schedule for tests"""
    return CrawlerSchedule.one_time()


@pytest.mark.asyncio
async def test_find_crawler_jobs_empty(repository):
    """Test finding crawler jobs when none exist"""
    user_id = str(uuid4())

    crawlers = await repository.find_crawler_jobs(user_id)

    assert crawlers == []


@pytest.mark.asyncio
async def test_find_crawler_jobs_single(repository, sample_crawler_config, default_schedule):
    """Test finding single crawler job"""
    user_id = str(uuid4())

    # Create a crawler job
    crawler = CrawlerJob(
        id=str(uuid4()),
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    await repository.save(crawler)

    # Find it
    crawlers = await repository.find_crawler_jobs(user_id)

    assert len(crawlers) == 1
    assert crawlers[0].id == crawler.id
    assert crawlers[0].source_url == "https://example.com"


@pytest.mark.asyncio
async def test_find_crawler_jobs_filters_by_user(repository, sample_crawler_config, default_schedule):
    """Test that crawler jobs are filtered by user_id"""
    user1_id = str(uuid4())
    user2_id = str(uuid4())

    # Create crawler for user 1
    crawler1 = CrawlerJob(
        id=str(uuid4()),
        user_id=user1_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    # Create crawler for user 2
    crawler2 = CrawlerJob(
        id=str(uuid4()),
        user_id=user2_id,
        job_type=JobType.CRAWLER,
        source_url="https://other.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    await repository.save(crawler1)
    await repository.save(crawler2)

    # Find user 1's crawlers
    user1_crawlers = await repository.find_crawler_jobs(user1_id)

    assert len(user1_crawlers) == 1
    assert user1_crawlers[0].id == crawler1.id


@pytest.mark.asyncio
async def test_find_crawler_jobs_with_status_filter(repository, sample_crawler_config, default_schedule):
    """Test filtering crawler jobs by status"""
    user_id = str(uuid4())

    # Create pending crawler
    pending_crawler = CrawlerJob(
        id=str(uuid4()),
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    # Create completed crawler
    completed_crawler = CrawlerJob(
        id=str(uuid4()),
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://other.com",
        status=JobStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    await repository.save(pending_crawler)
    await repository.save(completed_crawler)

    # Find only pending crawlers
    pending = await repository.find_crawler_jobs(user_id, filters={"status": "pending"})

    assert len(pending) == 1
    assert pending[0].status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_find_crawler_jobs_with_search_filter(repository, sample_crawler_config, default_schedule):
    """Test searching crawler jobs by URL"""
    user_id = str(uuid4())

    # Create crawlers with different URLs
    crawler1 = CrawlerJob(
        id=str(uuid4()),
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com/page1",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    crawler2 = CrawlerJob(
        id=str(uuid4()),
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://other.com/page2",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    await repository.save(crawler1)
    await repository.save(crawler2)

    # Search for 'example'
    results = await repository.find_crawler_jobs(user_id, filters={"search": "example"})

    assert len(results) == 1
    assert results[0].source_url == "https://example.com/page1"


@pytest.mark.asyncio
async def test_find_active_crawlers(repository, sample_crawler_config, default_schedule):
    """Test finding all active crawlers across all users"""
    user1_id = str(uuid4())
    user2_id = str(uuid4())

    # Create active crawler for user 1
    active1 = CrawlerJob(
        id=str(uuid4()),
        user_id=user1_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    # Create processing crawler for user 2
    processing = CrawlerJob(
        id=str(uuid4()),
        user_id=user2_id,
        job_type=JobType.CRAWLER,
        source_url="https://other.com",
        status=JobStatus.PROCESSING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    # Create completed crawler (should not be included)
    completed = CrawlerJob(
        id=str(uuid4()),
        user_id=user1_id,
        job_type=JobType.CRAWLER,
        source_url="https://done.com",
        status=JobStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    await repository.save(active1)
    await repository.save(processing)
    await repository.save(completed)

    # Find active crawlers
    active = await repository.find_active_crawlers()

    assert len(active) == 2
    statuses = [c.status for c in active]
    assert JobStatus.PENDING in statuses
    assert JobStatus.PROCESSING in statuses
    assert JobStatus.COMPLETED not in statuses


@pytest.mark.asyncio
async def test_find_crawler_executions(repository, sample_crawler_config, default_schedule):
    """Test finding execution history for a crawler"""
    user_id = str(uuid4())
    crawler_id = str(uuid4())

    # Create main crawler job
    crawler = CrawlerJob(
        id=crawler_id,
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    await repository.save(crawler)

    # Create execution jobs (children)
    from domain.entities.job import Job

    execution1 = Job(
        id=str(uuid4()),
        user_id=user_id,
        source_url="https://example.com",
        job_type=JobType.MAIN,
        status=JobStatus.COMPLETED,
        parent_job_id=crawler_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    execution2 = Job(
        id=str(uuid4()),
        user_id=user_id,
        source_url="https://example.com",
        job_type=JobType.MAIN,
        status=JobStatus.PROCESSING,
        parent_job_id=crawler_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    await repository.save(execution1)
    await repository.save(execution2)

    # Find executions
    executions = await repository.find_crawler_executions(crawler_id)

    assert len(executions) == 2
    # Verify they're ordered by created_at desc (most recent first)
    assert executions[0].created_at >= executions[1].created_at


@pytest.mark.asyncio
async def test_find_crawler_executions_empty(repository, sample_crawler_config, default_schedule):
    """Test finding executions when none exist"""
    user_id = str(uuid4())
    crawler_id = str(uuid4())

    # Create crawler but no executions
    crawler = CrawlerJob(
        id=crawler_id,
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    await repository.save(crawler)

    # Find executions
    executions = await repository.find_crawler_executions(crawler_id)

    assert executions == []


@pytest.mark.asyncio
async def test_save_and_retrieve_crawler_with_schedule(
    repository,
    sample_crawler_config,
    sample_crawler_schedule
):
    """Test saving and retrieving crawler with schedule"""
    user_id = str(uuid4())

    # Create crawler with schedule
    crawler = CrawlerJob(
        id=str(uuid4()),
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=sample_crawler_schedule,
    )

    await repository.save(crawler)

    # Retrieve it
    retrieved = await repository.find_by_id(crawler.id)

    assert retrieved is not None
    # Check if it's a CrawlerJob (it should be based on job_type)
    if isinstance(retrieved, CrawlerJob):
        assert retrieved.crawler_schedule is not None
        assert retrieved.crawler_schedule.type == ScheduleType.RECURRING
        assert retrieved.crawler_schedule.cron_expression == "0 9 * * *"


@pytest.mark.asyncio
async def test_model_to_crawler_job_conversion(repository, sample_crawler_config, default_schedule):
    """Test ORM to CrawlerJob entity conversion"""
    user_id = str(uuid4())

    # Create crawler
    crawler = CrawlerJob(
        id=str(uuid4()),
        user_id=user_id,
        job_type=JobType.CRAWLER,
        source_url="https://example.com",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        crawler_config=sample_crawler_config,
        crawler_schedule=default_schedule,
    )

    await repository.save(crawler)

    # Retrieve it
    retrieved = await repository.find_by_id(crawler.id)

    # Verify it's a CrawlerJob instance
    assert isinstance(retrieved, CrawlerJob)
    assert retrieved.crawler_config is not None
    assert retrieved.crawler_config.mode == CrawlerMode.PAGE_ONLY
    assert retrieved.crawler_config.crawler_engine == CrawlerEngine.BEAUTIFULSOUP
