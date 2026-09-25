"""
CrawlerJob Entity - Scheduled web crawler job

Extends Job entity with crawler-specific behavior.
Uses STI (Single Table Inheritance) pattern with job_type discriminator.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from domain.entities.job import Job, JobType, JobStatus
from domain.value_objects.crawler_config import CrawlerConfig
from domain.value_objects.crawler_schedule import CrawlerSchedule
from domain.services.url_normalizer_service import URLNormalizerService


@dataclass
class CrawlerJob(Job):
    """
    Crawler Job entity - represents a scheduled web crawler.

    Extends Job with crawler-specific configuration and scheduling.
    Uses job_type='crawler' discriminator in database (STI pattern).

    Business Rules:
    - URL cannot be localhost/private IP (security)
    - Cron expression must be valid if recurring schedule
    - Crawler config and schedule are immutable value objects
    - Can create child jobs for each execution
    """

    # Crawler-specific fields (stored as JSON in database)
    crawler_config: Optional[CrawlerConfig] = None
    crawler_schedule: Optional[CrawlerSchedule] = None

    def __post_init__(self):
        """
        Post-initialization validation.

        Forces job_type to CRAWLER and validates crawler-specific fields.
        """
        # Force crawler job type (STI discriminator)
        if self.job_type != JobType.CRAWLER:
            object.__setattr__(self, 'job_type', JobType.CRAWLER)

        # Call parent validation
        super().__post_init__()

        # Crawler-specific validation
        self._validate_crawler_fields()

    def _validate_crawler_fields(self):
        """Validate crawler-specific fields"""
        # Validate URL is not localhost/private IP
        if self.source_url:
            if not URLNormalizerService.validate_url(self.source_url, allow_localhost=False):
                raise ValueError(
                    f"Invalid crawler URL: {self.source_url}. "
                    "URL must be http/https and cannot be localhost or private IP."
                )

        # Validate crawler config is present
        if self.crawler_config is None:
            raise ValueError("CrawlerJob must have crawler_config")

        # Validate crawler schedule is present
        if self.crawler_schedule is None:
            raise ValueError("CrawlerJob must have crawler_schedule")

    # Status Management Methods

    def activate(self) -> None:
        """
        Activate crawler for scheduling.

        Sets status to QUEUED (ready to be picked up by scheduler).
        Updates timestamp.
        """
        object.__setattr__(self, 'status', JobStatus.QUEUED)
        object.__setattr__(self, 'updated_at', datetime.utcnow())

    def pause(self) -> None:
        """
        Pause crawler (stop scheduling new executions).

        Sets status to CANCELLED to prevent scheduler from picking it up.
        Maintains all configuration for potential resume.
        Does not affect currently running executions.
        """
        object.__setattr__(self, 'status', JobStatus.CANCELLED)
        object.__setattr__(self, 'updated_at', datetime.utcnow())

    def stop(self) -> None:
        """
        Permanently stop crawler.

        Sets status to CANCELLED and marks as terminal.
        Cannot be reactivated (would need to create new crawler).
        """
        object.__setattr__(self, 'status', JobStatus.CANCELLED)
        object.__setattr__(self, 'updated_at', datetime.utcnow())
        object.__setattr__(self, 'completed_at', datetime.utcnow())

    # Scheduling Methods

    def update_schedule(self, new_schedule: CrawlerSchedule) -> "CrawlerJob":
        """
        Update crawler schedule.

        Creates new CrawlerJob instance with updated schedule (immutable).

        Args:
            new_schedule: New schedule configuration

        Returns:
            New CrawlerJob instance with updated schedule

        Raises:
            ValueError: If new_schedule is invalid
        """
        # Validate new schedule
        if not isinstance(new_schedule, CrawlerSchedule):
            raise ValueError("new_schedule must be CrawlerSchedule instance")

        # Create new instance with updated schedule (dataclass is immutable)
        from dataclasses import replace
        return replace(
            self,
            crawler_schedule=new_schedule,
            updated_at=datetime.utcnow()
        )

    def schedule_next_execution(self, execution_id: Optional[str] = None) -> Job:
        """
        Create next execution job.

        Creates a child Job representing a single crawler execution.
        This child job will have parent_job_id pointing to this crawler.

        Args:
            execution_id: Optional explicit ID for execution job

        Returns:
            New Job instance for execution

        Raises:
            ValueError: If schedule is not recurring
        """
        if not self.crawler_schedule or not self.crawler_schedule.is_recurring:
            raise ValueError("Cannot schedule next execution for non-recurring crawler")

        # Calculate next execution time
        next_run = self.crawler_schedule.calculate_next_run()

        # Create execution job
        execution_job = Job(
            id=execution_id or f"exec-{self.id}-{datetime.utcnow().timestamp()}",
            user_id=self.user_id,
            job_type=JobType.DOWNLOAD,  # Execution jobs use DOWNLOAD type
            status=JobStatus.PENDING,
            source_url=self.source_url,
            parent_job_id=self.id,  # Link to crawler job
            name=f"{self.name or 'Crawler'} - Execution {next_run.isoformat()}",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        return execution_job

    def get_execution_history_query(self) -> dict:
        """
        Get query parameters for finding execution history.

        Returns:
            Dictionary with query parameters for repository
        """
        return {
            "parent_job_id": self.id,
            "order_by": "created_at",
            "order_direction": "desc",
        }

    # Query Methods

    def is_active(self) -> bool:
        """
        Check if crawler is active (eligible for scheduling).

        Returns:
            True if crawler can be scheduled
        """
        return self.status in [JobStatus.QUEUED, JobStatus.PENDING]

    def is_paused(self) -> bool:
        """
        Check if crawler is paused.

        Returns:
            True if crawler is paused
        """
        return self.status == JobStatus.CANCELLED and self.completed_at is None

    def is_stopped(self) -> bool:
        """
        Check if crawler is permanently stopped.

        Returns:
            True if crawler is stopped
        """
        return self.status == JobStatus.CANCELLED and self.completed_at is not None

    def should_execute_now(self, current_time: Optional[datetime] = None) -> bool:
        """
        Check if crawler should execute now.

        Args:
            current_time: Current time (defaults to now)

        Returns:
            True if crawler should execute
        """
        if not self.is_active():
            return False

        if not self.crawler_schedule:
            return False

        current_time = current_time or datetime.utcnow()

        # For one-time schedules
        if self.crawler_schedule.is_one_time:
            next_exec = self.crawler_schedule.next_execution
            return next_exec is not None and next_exec <= current_time

        # For recurring schedules
        if self.crawler_schedule.is_recurring:
            next_exec = self.crawler_schedule.next_execution
            return next_exec is not None and next_exec <= current_time

        return False

    # Information Methods

    def get_url_pattern(self) -> str:
        """
        Get normalized URL pattern for duplicate detection.

        Returns:
            URL pattern string
        """
        if not self.source_url:
            return ""

        return URLNormalizerService.generate_pattern(self.source_url)

    def get_normalized_url(self) -> str:
        """
        Get normalized URL.

        Returns:
            Normalized URL string
        """
        if not self.source_url:
            return ""

        return URLNormalizerService.normalize_url(self.source_url)

    def __repr__(self) -> str:
        """String representation for debugging"""
        status_str = self.status.value if self.status else "unknown"
        schedule_str = str(self.crawler_schedule) if self.crawler_schedule else "no schedule"
        return (
            f"CrawlerJob(id={self.id!r}, "
            f"url={self.source_url!r}, "
            f"status={status_str}, "
            f"schedule={schedule_str})"
        )
