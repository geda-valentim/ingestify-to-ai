"""
Tests for CrawlerSchedule value object
"""
import pytest
from datetime import datetime, timezone
from domain.value_objects.crawler_schedule import CrawlerSchedule
from domain.value_objects.crawler_enums import ScheduleType


def test_crawler_schedule_one_time():
    """Test creating one-time schedule"""
    schedule = CrawlerSchedule(
        type=ScheduleType.ONE_TIME,
        timezone="UTC",
    )

    assert schedule.type == ScheduleType.ONE_TIME
    assert schedule.cron_expression is None
    assert schedule.is_one_time
    assert not schedule.is_recurring


def test_crawler_schedule_recurring_requires_cron():
    """Test that recurring schedule requires cron expression"""
    with pytest.raises(ValueError, match="cron_expression is required"):
        CrawlerSchedule(
            type=ScheduleType.RECURRING,
            cron_expression=None,
        )


def test_crawler_schedule_one_time_rejects_cron():
    """Test that one-time schedule should not have cron"""
    with pytest.raises(ValueError, match="should not be set for one-time"):
        CrawlerSchedule(
            type=ScheduleType.ONE_TIME,
            cron_expression="0 9 * * *",
        )


def test_crawler_schedule_serialization():
    """Test JSON serialization"""
    exec_time = datetime(2025, 1, 20, 9, 0, 0, tzinfo=timezone.utc)

    schedule = CrawlerSchedule(
        type=ScheduleType.ONE_TIME,
        timezone="America/Sao_Paulo",
        next_runs=[exec_time],
    )

    data = schedule.to_dict()

    assert data["type"] == "one_time"
    assert data["timezone"] == "America/Sao_Paulo"
    assert len(data["next_runs"]) == 1
    assert data["next_runs"][0] == exec_time.isoformat()


def test_crawler_schedule_deserialization():
    """Test JSON deserialization"""
    data = {
        "type": "recurring",
        "cron_expression": "0 9 * * 1-5",
        "timezone": "UTC",
        "next_runs": ["2025-01-20T09:00:00+00:00"],
    }

    schedule = CrawlerSchedule.from_dict(data)

    assert schedule.type == ScheduleType.RECURRING
    assert schedule.cron_expression == "0 9 * * 1-5"
    assert schedule.timezone == "UTC"
    assert len(schedule.next_runs) == 1


def test_crawler_schedule_one_time_factory():
    """Test one_time factory method"""
    exec_time = datetime(2025, 2, 1, 10, 0, 0, tzinfo=timezone.utc)

    schedule = CrawlerSchedule.one_time(execution_time=exec_time)

    assert schedule.type == ScheduleType.ONE_TIME
    assert schedule.next_execution == exec_time


def test_crawler_schedule_recurring_factory():
    """Test recurring factory method"""
    schedule = CrawlerSchedule.recurring(
        cron_expression="0 7,9,12 * * 1,3,5",
        timezone="America/Sao_Paulo",
        calculate_next_runs=False,  # Skip calculation for unit test
    )

    assert schedule.type == ScheduleType.RECURRING
    assert schedule.cron_expression == "0 7,9,12 * * 1,3,5"
    assert schedule.timezone == "America/Sao_Paulo"


def test_crawler_schedule_next_execution():
    """Test getting next execution time"""
    exec_time = datetime(2025, 2, 1, 10, 0, 0, tzinfo=timezone.utc)

    schedule = CrawlerSchedule.one_time(execution_time=exec_time)

    assert schedule.next_execution == exec_time


def test_crawler_schedule_str():
    """Test string representation"""
    schedule_one_time = CrawlerSchedule.one_time()
    assert "One-time" in str(schedule_one_time)

    schedule_recurring = CrawlerSchedule.recurring(
        cron_expression="0 9 * * *",
        calculate_next_runs=False,
    )
    assert "Recurring" in str(schedule_recurring)
    assert "0 9 * * *" in str(schedule_recurring)
