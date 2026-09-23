"""SCRUM-55 AC2/AC3/AC4/AC6: pure venue-search rules, without a database.

Multi-day requested periods (1 Dec 2026 10:00 through 3 Dec 2026 12:00): the
domain helpers take tz-aware datetimes for the requested period and wall-clock
`datetime.time` for daily operating hours. Each test names its Test Case ID so
the CSV row maps to exactly one test.

Expected domain surface:
    VenueSearchCriteria: minimum_capacity, location, required_facilities,
        required_accessibility, required_layout
    SearchableVenue: maximum_capacity, location, facilities,
        accessibility_features, supported_layouts
    venue_matches_criteria(venue, criteria) -> bool  (static filters only;
        active status and persisted availability are integration concerns)
    is_within_operating_hours(opens_at, closes_at, requested_start, requested_end) -> bool
        (opens/closes are `datetime.time`; requested bounds are tz-aware datetimes;
        only their wall-clock time-of-day must fit inside opening hours, so a
        multi-day request is within hours when its start time-of-day and end
        time-of-day are both inside; end equal to closing is allowed)
    intervals_overlap(a_start, a_end, b_start, b_end) -> bool
        (tz-aware datetimes; half-open [start, end), adjacent is not overlap)
    booking_blocks_availability(status) -> bool
        (True for confirmed, False for pending)
"""

from datetime import UTC, datetime, time

import pytest

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

    within = is_within_operating_hours(
        opens, closes, _dt(1, 20), _dt(3, 22, 0)
    )
    just_outside = is_within_operating_hours(
        opens, closes, _dt(1, 20), _dt(3, 22, 1)
    )

    assert within is True
    assert just_outside is False


# ------------------------------------------------------- TC-55-AC3-04


@pytest.mark.story("SCRUM-55")
def test_tc55_ac3_04_request_starting_before_opening_is_outside() -> None:
    assert (
        is_within_operating_hours(time(8, 0), time(22, 0), _dt(1, 7, 59), _dt(3, 9, 0))
        is False
    )


# ------------------------------------------------------- TC-55-AC4-03


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 12, day, hour, minute, tzinfo=UTC)


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
    assert booking_blocks_availability("pending") is False


@pytest.mark.story("SCRUM-55")
def test_tc55_ac6_02_confirmed_request_blocks_availability() -> None:
    # Contrast case for the same status rule: only a confirmed hold blocks search.
    assert booking_blocks_availability("confirmed") is True
