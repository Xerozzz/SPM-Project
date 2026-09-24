"""SCRUM-62: pure validation for venue closure periods."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from domain.venue_unavailability import VenueUnavailabilityFields, validate_unavailability


def fields(**overrides: Any) -> VenueUnavailabilityFields:
    start = datetime(2026, 10, 1, 9, tzinfo=UTC)
    values: dict[str, Any] = {
        "starts_at": start,
        "ends_at": start + timedelta(hours=2),
        "reason": "Air-conditioning maintenance",
    }
    values.update(overrides)
    return VenueUnavailabilityFields(**values)


@pytest.mark.story("SCRUM-62")
def test_valid_unavailability_has_no_problems() -> None:
    assert validate_unavailability(fields()) == []


@pytest.mark.story("SCRUM-62")
def test_end_must_be_after_start() -> None:
    start = datetime(2026, 10, 1, 9, tzinfo=UTC)
    assert (
        validate_unavailability(fields(ends_at=start)).pop().reason
        == "must be after the start time"
    )


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_datetimes_must_be_utc(field: str) -> None:
    naive = datetime.fromisoformat("2026-10-01T09:00:00")
    problems = validate_unavailability(fields(**{field: naive}))
    assert (field, "must be a timezone-aware UTC datetime") in {
        (problem.field, problem.reason) for problem in problems
    }


@pytest.mark.story("SCRUM-62")
def test_reason_is_required() -> None:
    assert validate_unavailability(fields(reason="  ")).pop().field == "reason"
