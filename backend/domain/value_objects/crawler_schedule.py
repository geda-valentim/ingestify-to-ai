"""
CrawlerSchedule Value Object - Crawler scheduling configuration
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
from domain.value_objects.crawler_enums import ScheduleType


@dataclass(frozen=True)
class CrawlerSchedule:
    """
    Value Object for crawler scheduling configuration.

    Immutable scheduling settings for recurring or one-time crawler executions.
    Supports cron expressions with timezone awareness.
    """
    type: ScheduleType
    cron_expression: Optional[str] = None
    timezone: str = "UTC"
    next_runs: List[datetime] = field(default_factory=list)

    def __post_init__(self):
        """Validate schedule configuration"""
        self._validate_cron_and_type()
        self._validate_timezone()

    def _validate_cron_and_type(self):
        """Validate cron expression is required for recurring schedules"""
        if self.type == ScheduleType.RECURRING:
            if not self.cron_expression:
                raise ValueError("cron_expression is required for recurring schedules")

            # Validate cron expression format
            try:
                from croniter import croniter
                if not croniter.is_valid(self.cron_expression):
                    raise ValueError(f"Invalid cron expression: {self.cron_expression}")
            except ImportError:
                # If croniter not available, skip validation
                # (will be caught when trying to calculate next runs)
                pass

        elif self.type == ScheduleType.ONE_TIME:
            if self.cron_expression:
                raise ValueError("cron_expression should not be set for one-time schedules")

    def _validate_timezone(self):
        """Validate timezone is valid"""
        try:
            import pytz
            pytz.timezone(self.timezone)
        except ImportError:
            # If pytz not available, skip validation
            pass
        except Exception as e:
            raise ValueError(f"Invalid timezone '{self.timezone}': {e}")

    def calculate_next_run(self, base_time: Optional[datetime] = None) -> datetime:
        """
        Calculate next execution time from cron expression.

        Args:
            base_time: Base time to calculate from (defaults to now in UTC)

        Returns:
            Next execution datetime (UTC)

        Raises:
            ValueError: If schedule is not recurring or cron is invalid
        """
        if self.type != ScheduleType.RECURRING:
            raise ValueError("Cannot calculate next run for non-recurring schedule")

        if not self.cron_expression:
            raise ValueError("cron_expression is required to calculate next run")

        try:
            from croniter import croniter
            import pytz
        except ImportError as e:
            raise ImportError(f"Required package not installed: {e}")

        # Get base time in specified timezone
        if base_time is None:
            base_time = datetime.now(timezone.utc)

        tz = pytz.timezone(self.timezone)

        # Convert base_time to schedule timezone if needed
        if base_time.tzinfo is None:
            base_time = tz.localize(base_time)
        else:
            base_time = base_time.astimezone(tz)

        # Calculate next run
        cron = croniter(self.cron_expression, base_time)
        next_run = cron.get_next(datetime)

        # Convert back to UTC
        return next_run.astimezone(timezone.utc)

    def calculate_next_n_runs(self, n: int = 5, base_time: Optional[datetime] = None) -> List[datetime]:
        """
        Calculate next N execution times.

        Args:
            n: Number of future runs to calculate
            base_time: Base time to calculate from (defaults to now in UTC)

        Returns:
            List of next N execution datetimes (UTC)

        Raises:
            ValueError: If schedule is not recurring or n < 1
        """
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")

        if self.type != ScheduleType.RECURRING:
            return []

        try:
            from croniter import croniter
            import pytz
        except ImportError as e:
            raise ImportError(f"Required package not installed: {e}")

        if base_time is None:
            base_time = datetime.now(timezone.utc)

        tz = pytz.timezone(self.timezone)

        # Convert base_time to schedule timezone
        if base_time.tzinfo is None:
            base_time = tz.localize(base_time)
        else:
            base_time = base_time.astimezone(tz)

        # Calculate next N runs
        cron = croniter(self.cron_expression, base_time)
        next_runs = []
        for _ in range(n):
            next_run = cron.get_next(datetime)
            next_runs.append(next_run.astimezone(timezone.utc))

        return next_runs

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "type": self.type.value,
            "cron_expression": self.cron_expression,
            "timezone": self.timezone,
            "next_runs": [dt.isoformat() for dt in self.next_runs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlerSchedule":
        """
        Create CrawlerSchedule from dictionary.

        Args:
            data: Dictionary with schedule config keys

        Returns:
            CrawlerSchedule instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        if not isinstance(data, dict):
            raise ValueError("Input must be a dictionary")

        # Parse schedule type
        schedule_type = ScheduleType(data["type"])

        # Parse next_runs
        next_runs = []
        if "next_runs" in data and data["next_runs"]:
            for dt_str in data["next_runs"]:
                if isinstance(dt_str, str):
                    next_runs.append(datetime.fromisoformat(dt_str))
                elif isinstance(dt_str, datetime):
                    next_runs.append(dt_str)

        return cls(
            type=schedule_type,
            cron_expression=data.get("cron_expression"),
            timezone=data.get("timezone", "UTC"),
            next_runs=next_runs,
        )

    @classmethod
    def one_time(cls, execution_time: Optional[datetime] = None) -> "CrawlerSchedule":
        """
        Create one-time schedule.

        Args:
            execution_time: When to execute (defaults to now)

        Returns:
            CrawlerSchedule for one-time execution
        """
        if execution_time is None:
            execution_time = datetime.now(timezone.utc)

        return cls(
            type=ScheduleType.ONE_TIME,
            next_runs=[execution_time],
        )

    @classmethod
    def recurring(
        cls,
        cron_expression: str,
        timezone: str = "UTC",
        calculate_next_runs: bool = True,
        next_runs_count: int = 5
    ) -> "CrawlerSchedule":
        """
        Create recurring schedule.

        Args:
            cron_expression: Cron expression (e.g., "0 9 * * 1-5" for weekdays at 9am)
            timezone: Timezone for cron expression (default: UTC)
            calculate_next_runs: Whether to pre-calculate next runs
            next_runs_count: Number of next runs to pre-calculate

        Returns:
            CrawlerSchedule for recurring execution
        """
        schedule = cls(
            type=ScheduleType.RECURRING,
            cron_expression=cron_expression,
            timezone=timezone,
        )

        # Calculate next runs if requested
        if calculate_next_runs:
            try:
                next_runs = schedule.calculate_next_n_runs(next_runs_count)
                # Create new instance with next_runs (immutable, so need to recreate)
                # Use object.__setattr__ to bypass frozen dataclass
                import copy
                schedule_copy = copy.copy(schedule)
                object.__setattr__(schedule_copy, 'next_runs', next_runs)
                return schedule_copy
            except ImportError:
                # If croniter/pytz not available, return without next_runs
                pass

        return schedule

    @property
    def is_recurring(self) -> bool:
        """Check if schedule is recurring"""
        return self.type == ScheduleType.RECURRING

    @property
    def is_one_time(self) -> bool:
        """Check if schedule is one-time"""
        return self.type == ScheduleType.ONE_TIME

    @property
    def next_execution(self) -> Optional[datetime]:
        """Get next scheduled execution time"""
        return self.next_runs[0] if self.next_runs else None

    def __str__(self) -> str:
        """String representation"""
        if self.is_recurring:
            return f"Recurring: {self.cron_expression} ({self.timezone})"
        return f"One-time: {self.next_execution or 'Not scheduled'}"
