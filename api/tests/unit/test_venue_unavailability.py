"""SCRUM-62: pure validation for venue closure periods."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

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
    assert (field, "must be given in UTC") in {
        (problem.field, problem.reason) for problem in problems
    }


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_datetimes_with_non_utc_offsets_are_rejected(field: str) -> None:
    singapore_time = datetime(2026, 10, 1, 17, tzinfo=timezone(timedelta(hours=8)))
    problems = validate_unavailability(fields(**{field: singapore_time}))
    assert (field, "must be given in UTC") in {
        (problem.field, problem.reason) for problem in problems
    }


@pytest.mark.story("SCRUM-62")
def test_datetimes_with_zoneinfo_utc_are_valid() -> None:
    start = datetime(2026, 10, 1, 9, tzinfo=ZoneInfo("UTC"))
    utc_fields = fields(starts_at=start, ends_at=start + timedelta(hours=2))
    assert validate_unavailability(utc_fields) == []


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_datetimes_are_required(field: str) -> None:
    problems = validate_unavailability(fields(**{field: None}))
    assert (field, "is required") in {(problem.field, problem.reason) for problem in problems}


@pytest.mark.story("SCRUM-62")
def test_reason_is_required() -> None:
    assert validate_unavailability(fields(reason="  ")).pop().field == "reason"
