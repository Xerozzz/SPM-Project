"""SCRUM-55 AC2/AC3/AC4/AC6: pure venue-search rules, without a database.

Multi-day requested periods (1 Dec 2026 10:00 through 3 Dec 2026 12:00 SGT): the
domain helpers take tz-aware datetimes for the requested period and wall-clock
`datetime.time` for daily operating hours (local SGT wall-clock, see
domain/venue.py). Each test names its Test Case ID so
the CSV row maps to exactly one test.

Expected domain surface:
    VenueSearchCriteria: minimum_capacity, location, required_facilities,
        required_accessibility, required_layout
    SearchableVenue: maximum_capacity, location, facilities,
        accessibility_features, supported_layouts
    venue_matches_criteria(venue, criteria) -> bool  (static filters only;
        active status and persisted availability are integration concerns)
    is_within_operating_hours(opens_at, closes_at, requested_start, requested_end) -> bool
        (opens/closes are local SGT `datetime.time`; requested bounds are tz-aware
        datetimes converted to SGT before their time-of-day is compared, so a
        multi-day request is within hours when its SGT start time-of-day and end
        time-of-day are both inside and the local end is not earlier in the day
        than the local start (a request running through the closed night is
        outside); end equal to closing is allowed)
    intervals_overlap(a_start, a_end, b_start, b_end) -> bool
        (tz-aware datetimes; half-open [start, end), adjacent is not overlap)
    booking_blocks_availability(status: BookingStatus) -> bool
        (True for confirmed, False for pending)
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from domain.venue_booking import BookingStatus
from domain.venue_search import (
    SearchableVenue,
    VenueSearchCriteria,
    booking_blocks_availability,
    intervals_overlap,
    is_within_operating_hours,
    venue_matches_criteria,
)


def base_venue(**overrides: object) -> SearchableVenue:
    """A venue matching every AC2 criterion; pass field=value to break exactly one."""
    values: dict[str, object] = {
        "maximum_capacity": 100,
        "location": "Level 2, School of Computing",
        "facilities": ["Projector"],
        "accessibility_features": ["Step-free access"],
        "supported_layouts": ["theatre"],
    }
    values.update(overrides)
    return SearchableVenue(**values)  # type: ignore[arg-type]


def base_criteria() -> VenueSearchCriteria:
    """The AC2 search criteria every base venue satisfies."""
    return VenueSearchCriteria(
        minimum_capacity=100,
        location="Level 2, School of Computing",
        required_facilities=["Projector"],
        required_accessibility=["Step-free access"],
        required_layout="theatre",
    )


# ------------------------------------------------------- TC-55-AC2-02


@pytest.mark.story("SCRUM-55")
def test_tc55_ac2_02_matching_venue_matches_and_step_free_gap_does_not() -> None:
    criteria = base_criteria()

    assert venue_matches_criteria(base_venue(), criteria) is True
    without_access = base_venue(accessibility_features=[])
    assert venue_matches_criteria(without_access, criteria) is False


# ------------------------------------------------------- TC-55-AC2-03


@pytest.mark.story("SCRUM-55")
def test_tc55_ac2_03_base_venue_matches() -> None:
    assert venue_matches_criteria(base_venue(), base_criteria()) is True


@pytest.mark.story("SCRUM-55")
@pytest.mark.parametrize(
    ("venue_kwargs", "case_id"),
    [
        ({"maximum_capacity": 99}, "capacity-one-below-minimum"),
        ({"location": "Level 3, Elsewhere"}, "different-location"),
        ({"facilities": []}, "missing-projector"),
        ({"accessibility_features": []}, "missing-step-free-access"),
        ({"supported_layouts": ["classroom"]}, "missing-theatre-layout"),
    ],
)
def test_tc55_ac2_03_each_single_criterion_gap_excludes(
    venue_kwargs: dict[str, object], case_id: str
) -> None:
    del case_id
    venue = base_venue(**venue_kwargs)

    assert venue_matches_criteria(venue, base_criteria()) is False


# ------------------------------------------------------- TC-55-AC3-03


@pytest.mark.story("SCRUM-55")
def test_tc55_ac3_03_closing_boundary_is_inclusive() -> None:
    opens, closes = time(8, 0), time(22, 0)

    within = is_within_operating_hours(opens, closes, _dt(1, 20), _dt(3, 22, 0))
    just_outside = is_within_operating_hours(opens, closes, _dt(1, 20), _dt(3, 22, 1))

    assert within is True
    assert just_outside is False


# ------------------------------------------------------- TC-55-AC3-04


@pytest.mark.story("SCRUM-55")
def test_tc55_ac3_04_request_starting_before_opening_is_outside() -> None:
    assert is_within_operating_hours(time(8, 0), time(22, 0), _dt(1, 7, 59), _dt(3, 9, 0)) is False


@pytest.mark.story("SCRUM-55")
def test_tc55_ac3_06_overnight_request_running_through_closed_night_is_outside() -> None:
    # Both endpoints look open (21:00 and 08:30 are inside 08:00-22:00), but the
    # period runs through the closed night, so the venue must be excluded.
    assert is_within_operating_hours(time(8, 0), time(22, 0), _dt(3, 21), _dt(4, 8, 30)) is False


@pytest.mark.story("SCRUM-55")
def test_tc55_ac3_08_inverted_requested_period_is_outside_hours() -> None:
    # An end at or before the start is not a real period; the domain refuses it
    # (the router reports the same shape as a 422 before it gets here).
    assert is_within_operating_hours(time(8, 0), time(22, 0), _dt(1, 10), _dt(1, 10)) is False
    assert is_within_operating_hours(time(8, 0), time(22, 0), _dt(3, 12), _dt(1, 10)) is False


# ------------------------------------------------------- TC-55-AC4-03


_SGT = ZoneInfo("Asia/Singapore")


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    """A tz-aware instant whose SGT wall-clock reads day/hour:minute."""
    return datetime(2026, 12, day, hour, minute, tzinfo=_SGT)


@pytest.mark.story("SCRUM-55")
@pytest.mark.parametrize(
    ("start", "end", "expected", "case_id"),
    [
        (_dt(2, 11), _dt(2, 13), True, "starts-inside"),
        (_dt(2, 9), _dt(2, 11), True, "ends-inside"),
        (_dt(2, 9), _dt(2, 13), True, "contains-booking"),
        (_dt(2, 10, 30), _dt(2, 11, 30), True, "contained-by-booking"),
        (_dt(1, 10), _dt(3, 12), True, "multi-day-contains-booking"),
        (_dt(2, 12), _dt(2, 14), False, "adjacent-is-not-overlap"),
    ],
)
def test_tc55_ac4_03_interval_overlap_matrix(
    start: datetime, end: datetime, expected: bool, case_id: str
) -> None:
    del case_id
    booking_start, booking_end = _dt(2, 10), _dt(2, 12)

    assert intervals_overlap(booking_start, booking_end, start, end) is expected


# ------------------------------------------------------- TC-55-AC6-02


@pytest.mark.story("SCRUM-55")
def test_tc55_ac6_02_pending_request_does_not_block_availability() -> None:
    assert booking_blocks_availability(BookingStatus.PENDING) is False


@pytest.mark.story("SCRUM-55")
def test_tc55_ac6_02_confirmed_request_blocks_availability() -> None:
    # Contrast case for the same status rule: only a confirmed hold blocks search.
    assert booking_blocks_availability(BookingStatus.CONFIRMED) is True


# ------------------------------------------------------- TC-55-AC2-04


@pytest.mark.story("SCRUM-55")
def test_tc55_ac2_04_no_layout_constraint_matches_any_layout() -> None:
    criteria = VenueSearchCriteria(
        minimum_capacity=100,
        location="Level 2, School of Computing",
        required_facilities=["Projector"],
        required_accessibility=["Step-free access"],
        required_layout=None,
    )

    assert venue_matches_criteria(base_venue(), criteria) is True


@pytest.mark.story("SCRUM-55")
def test_tc55_ac2_05_free_text_matching_ignores_case_and_whitespace() -> None:
    criteria = VenueSearchCriteria(
        minimum_capacity=100,
        location="  level 2, school of computing ",
        required_facilities=["  PROJECTOR "],
        required_accessibility=["step-free ACCESS"],
        required_layout=" THEATRE ",
    )

    assert venue_matches_criteria(base_venue(), criteria) is True


# ------------------------------------------------------- TC-55-AC3-05


@pytest.mark.story("SCRUM-55")
@pytest.mark.parametrize("index", [0, 1])
def test_tc55_ac3_05_naive_requested_period_is_rejected(index: int) -> None:
    bounds = [_dt(1, 10), _dt(3, 12)]
    bounds[index] = bounds[index].replace(tzinfo=None)

    with pytest.raises(ValueError, match="timezone-aware"):
        is_within_operating_hours(time(8, 0), time(22, 0), bounds[0], bounds[1])


# ------------------------------------------------------- TC-55-AC4-04


@pytest.mark.story("SCRUM-55")
@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_tc55_ac4_04_naive_interval_bounds_are_rejected(index: int) -> None:
    bounds = [_dt(2, 10), _dt(2, 12), _dt(2, 11), _dt(2, 13)]
    bounds[index] = bounds[index].replace(tzinfo=None)

    with pytest.raises(ValueError, match="timezone-aware"):
        intervals_overlap(bounds[0], bounds[1], bounds[2], bounds[3])
