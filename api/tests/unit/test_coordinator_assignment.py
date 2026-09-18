"""Round-robin coordinator selection (SCRUM-34): pure, no I/O, no database."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from domain.coordinator_assignment import (
    NoAvailableCoordinatorError,
    org_day_bounds,
    select_next_coordinator,
)

_A, _B, _C = uuid4(), uuid4(), uuid4()


@pytest.mark.story("SCRUM-34")
def test_first_assignment_ever_picks_the_front_of_the_pool() -> None:
    assert select_next_coordinator([_A, _B, _C], None, set()) == _A


@pytest.mark.story("SCRUM-34")
def test_rotation_continues_after_whoever_was_assigned_last() -> None:
    assert select_next_coordinator([_A, _B, _C], _A, set()) == _B


@pytest.mark.story("SCRUM-34")
def test_boundary_rotation_wraps_from_the_last_slot_back_to_the_front() -> None:
    assert select_next_coordinator([_A, _B, _C], _C, set()) == _A


@pytest.mark.story("SCRUM-34")
def test_unavailable_coordinator_is_skipped_in_favour_of_the_next() -> None:
    assert select_next_coordinator([_A, _B, _C], _A, {_B}) == _C


@pytest.mark.story("SCRUM-34")
def test_last_assigned_coordinator_no_longer_in_the_pool_restarts_from_the_front() -> None:
    departed = uuid4()
    assert select_next_coordinator([_A, _B, _C], departed, set()) == _A


@pytest.mark.story("SCRUM-34")
def test_conflict_when_every_active_coordinator_is_already_busy_that_date() -> None:
    with pytest.raises(NoAvailableCoordinatorError):
        select_next_coordinator([_A, _B], None, {_A, _B})


@pytest.mark.story("SCRUM-34")
def test_conflict_when_there_is_no_active_coordinator_at_all() -> None:
    with pytest.raises(NoAvailableCoordinatorError):
        select_next_coordinator([], None, set())


@pytest.mark.story("SCRUM-34")
def test_org_day_bounds_covers_the_whole_calendar_day_and_nothing_else() -> None:
    start, end = org_day_bounds(datetime(2026, 11, 3, 15, 30, tzinfo=UTC))

    assert start == datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 3, 16, 0, tzinfo=UTC)


@pytest.mark.story("SCRUM-34")
def test_org_day_bounds_uses_singapore_time_not_utc() -> None:
    moment = datetime(2026, 6, 30, 16, 30, tzinfo=UTC)
    start, end = org_day_bounds(moment)
    assert start == datetime(2026, 6, 30, 16, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 1, 16, 0, tzinfo=UTC)


@pytest.mark.story("SCRUM-34")
def test_org_day_bounds_converts_a_non_utc_moment_to_its_sgt_calendar_date() -> None:
    # 23:30 in UTC+2 on 3 Nov is 21:30 UTC on 3 Nov, which is 05:30 SGT on 4 Nov —
    # a different calendar day in Singapore even though it's still 3 Nov in UTC+2.
    plus_two = timezone(timedelta(hours=2))
    start, end = org_day_bounds(datetime(2026, 11, 3, 23, 30, tzinfo=plus_two))

    assert start == datetime(2026, 11, 3, 16, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 4, 16, 0, tzinfo=UTC)


@pytest.mark.story("SCRUM-34")
def test_org_day_bounds_rejects_a_naive_datetime() -> None:
    naive = datetime(2026, 11, 3, 12, 0, tzinfo=UTC).replace(tzinfo=None)

    with pytest.raises(ValueError, match="timezone-aware"):
        org_day_bounds(naive)
