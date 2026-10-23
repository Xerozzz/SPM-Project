"""SCRUM-113's pure deadline and non-Confirmed intake guards."""

from datetime import UTC, datetime, timedelta

import pytest

from domain.event_status import EventStatus
from domain.registration_intake import (
    RegistrationIntakeError,
    Settings,
    intake_is_open,
    validate_extension,
    validate_open,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


@pytest.mark.story("SCRUM-113")
def test_intake_closes_at_its_deadline_and_for_every_non_confirmed_state() -> None:
    """A deadline and a replanning status are backend guards, not UI hints."""
    settings = Settings(NOW - timedelta(hours=1), NOW, None)
    assert not intake_is_open(EventStatus.CONFIRMED, settings, NOW)
    assert not intake_is_open(EventStatus.APPROVED, Settings(NOW, None, None), NOW)


@pytest.mark.story("SCRUM-113")
def test_suspension_requires_explicit_reopening_even_after_reconfirmation() -> None:
    settings = Settings(NOW - timedelta(hours=1), None, NOW)
    assert not intake_is_open(EventStatus.CONFIRMED, settings, NOW + timedelta(hours=1))


@pytest.mark.story("SCRUM-113")
def test_deadlines_must_be_future_and_extensions_must_move_forward() -> None:
    with pytest.raises(RegistrationIntakeError):
        validate_open(NOW, NOW)
    with pytest.raises(RegistrationIntakeError):
        validate_extension(Settings(NOW, NOW + timedelta(hours=1), None), NOW, NOW)
    with pytest.raises(RegistrationIntakeError):
        validate_extension(Settings(NOW, None, None), NOW + timedelta(hours=2), NOW)
