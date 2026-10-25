"""DOCLING_PAGE_WINDOW and the window time limit (spec 0022; inert until wired)."""

import pytest
from pydantic import ValidationError

from shared.config import Settings


def make(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_default_window_is_one_and_limit_equals_the_conversion_timeout():
    settings = make()
    assert settings.docling_page_window == 1
    assert settings.docling_window_time_limit_seconds is None
    assert settings.docling_window_time_limit == settings.conversion_timeout_seconds


@pytest.mark.parametrize("window", [0, 9])
def test_window_out_of_range_is_refused(window):
    with pytest.raises(ValidationError):
        make(docling_page_window=window)


def test_window_multiplies_the_conversion_timeout():
    settings = make(docling_page_window=4, conversion_timeout_seconds=300)
    assert settings.docling_window_time_limit == 1200


def test_window_limit_must_stay_below_the_visibility_timeout():
    with pytest.raises(ValueError, match="DOCLING_WINDOW_TIME_LIMIT_SECONDS"):
        make(docling_page_window=4, conversion_timeout_seconds=3600, celery_visibility_timeout_seconds=14400)


def test_explicit_limit_above_visibility_is_refused():
    with pytest.raises(ValueError, match="DOCLING_WINDOW_TIME_LIMIT_SECONDS"):
        make(docling_window_time_limit_seconds=20000, celery_visibility_timeout_seconds=14400)


def test_explicit_limit_below_visibility_passes():
    settings = make(docling_page_window=4, docling_window_time_limit_seconds=5000)
    assert settings.docling_window_time_limit == 5000


def test_empty_explicit_limit_is_unset(monkeypatch):
    monkeypatch.setenv("DOCLING_WINDOW_TIME_LIMIT_SECONDS", "")
    assert make().docling_window_time_limit_seconds is None


@pytest.mark.parametrize("value", [0, -5])
def test_non_positive_explicit_limit_is_refused(value):
    with pytest.raises(ValidationError):
        make(docling_window_time_limit_seconds=value)
