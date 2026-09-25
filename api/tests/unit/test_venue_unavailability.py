"""SCRUM-62: pure validation for venue closure periods."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from domain.validation import FieldProblem
from domain.venue_unavailability import VenueUnavailabilityFields, validate_unavailability

NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


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
    assert validate_unavailability(fields(), NOW) == []


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (-1, [FieldProblem("ends_at", "must be after the start time")]),
        (0, [FieldProblem("ends_at", "must be after the start time")]),
        (1, []),
    ],
)
def test_end_time_boundary_is_just_after_start(offset: int, expected: list[FieldProblem]) -> None:
    start = datetime(2026, 10, 1, 9, tzinfo=UTC)
    closure = fields(ends_at=start + timedelta(microseconds=offset))
    assert validate_unavailability(closure, NOW) == expected


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize(
    ("starts_at", "ends_at", "expected"),
    [
        (NOW - timedelta(days=1), NOW + timedelta(days=1), []),
        (
            NOW - timedelta(days=2),
            NOW,
            [FieldProblem("ends_at", "must be in the future")],
        ),
        (
            NOW - timedelta(days=3),
            NOW - timedelta(days=1),
            [FieldProblem("ends_at", "must be in the future")],
        ),
    ],
)
def test_end_time_must_be_in_the_future(
    starts_at: datetime, ends_at: datetime, expected: list[FieldProblem]
) -> None:
    assert validate_unavailability(fields(starts_at=starts_at, ends_at=ends_at), NOW) == expected


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_datetimes_must_be_utc(field: str) -> None:
    naive = datetime.fromisoformat("2026-10-01T09:00:00")
    problems = validate_unavailability(fields(**{field: naive}), NOW)
    assert (field, "must be given in UTC") in {
        (problem.field, problem.reason) for problem in problems
    }


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_datetimes_with_non_utc_offsets_are_rejected(field: str) -> None:
    singapore_time = datetime(2026, 10, 1, 17, tzinfo=timezone(timedelta(hours=8)))
    problems = validate_unavailability(fields(**{field: singapore_time}), NOW)
    assert (field, "must be given in UTC") in {
        (problem.field, problem.reason) for problem in problems
    }


@pytest.mark.story("SCRUM-62")
def test_datetimes_with_zoneinfo_utc_are_valid() -> None:
    start = datetime(2026, 10, 1, 9, tzinfo=ZoneInfo("UTC"))
    utc_fields = fields(starts_at=start, ends_at=start + timedelta(hours=2))
    assert validate_unavailability(utc_fields, NOW) == []


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize("field", ["starts_at", "ends_at"])
def test_datetimes_are_required(field: str) -> None:
    problems = validate_unavailability(fields(**{field: None}), NOW)
    assert (field, "is required") in {(problem.field, problem.reason) for problem in problems}


@pytest.mark.story("SCRUM-62")
def test_reason_is_required() -> None:
    assert validate_unavailability(fields(reason="  "), NOW) == [
        FieldProblem("reason", "is required")
    ]
