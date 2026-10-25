"""Admission limit settings (spec 0022): parsed only, nothing consumes them yet."""

import pytest
from pydantic import ValidationError

from shared.config import Settings, _format_settings_error

FIELDS = {
    "ADMISSION_MAX_PAGES_PER_PDF": "admission_max_pages_per_pdf",
    "ADMISSION_MAX_PAGES_PER_CLIENT": "admission_max_pages_per_client",
    "ADMISSION_MAX_WAITING_PER_CLIENT": "admission_max_waiting_per_client",
    "ADMISSION_GLOBAL_SLOTS": "admission_global_slots",
}


def make(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_every_limit_is_unlimited_by_default():
    settings = make()
    assert all(getattr(settings, name) is None for name in FIELDS.values())


@pytest.mark.parametrize("env", FIELDS)
@pytest.mark.parametrize("raw", ["", "unlimited", "UNLIMITED", " -1 ", " Unlimited "])
def test_unlimited_spellings_become_none(monkeypatch, env, raw):
    monkeypatch.setenv(env, raw)
    assert getattr(make(), FIELDS[env]) is None


@pytest.mark.parametrize("env", FIELDS)
def test_a_positive_number_is_the_limit(monkeypatch, env):
    monkeypatch.setenv(env, "3")
    assert getattr(make(), FIELDS[env]) == 3


@pytest.mark.parametrize("raw", ["0", "-2", "abc", "1.5"])
def test_invalid_values_are_refused(monkeypatch, raw):
    monkeypatch.setenv("ADMISSION_GLOBAL_SLOTS", raw)
    with pytest.raises(ValidationError):
        make()


def test_zero_message_explains_why():
    with pytest.raises(ValidationError, match="would block everything"):
        make(admission_max_pages_per_pdf=0)


def test_a_boolean_is_refused():
    with pytest.raises(ValidationError):
        make(admission_max_pages_per_pdf=True)


def test_minus_one_kwarg_is_unlimited():
    assert make(admission_max_pages_per_client=-1).admission_max_pages_per_client is None


def test_the_error_names_the_variable():
    with pytest.raises(ValidationError) as info:
        make(admission_max_pages_per_pdf=0)
    assert "ADMISSION_MAX_PAGES_PER_PDF" in _format_settings_error(info.value)
