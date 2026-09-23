"""SCRUM-55 AC2/AC3/AC4/AC6: pure venue-search rules, without a database.

TDD red phase: the domain helpers imported here (`domain/venue_search.py`) do not exist
yet. Each test names its Test Case ID so the CSV row maps to exactly one test. When the
implementation lands, these tests must pass unchanged.

Expected domain surface (to be built):
    VenueSearchCriteria: minimum_capacity, location, required_facilities,
        required_accessibility, required_layout
    SearchableVenue: maximum_capacity, location, facilities,
        accessibility_features, supported_layouts
    venue_matches_criteria(venue, criteria) -> bool  (static filters only;
        active status and persisted availability are integration concerns)
    is_within_operating_hours(opens_at, closes_at, requested_start, requested_end) -> bool
        (all `datetime.time`; end equal to closing is allowed)
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

    assert is_within_operating_hours(opens, closes, time(20, 0), time(22, 0)) is True
    assert is_within_operating_hours(opens, closes, time(20, 0), time(22, 1)) is False


# ------------------------------------------------------- TC-55-AC3-04


@pytest.mark.story("SCRUM-55")
def test_tc55_ac3_04_request_starting_before_opening_is_outside() -> None:
    assert is_within_operating_hours(time(8, 0), time(22, 0), time(7, 59), time(9, 0)) is False


# ------------------------------------------------------- TC-55-AC4-03


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 12, 1, hour, minute, tzinfo=UTC)


@pytest.mark.story("SCRUM-55")
@pytest.mark.parametrize(
    ("start", "end", "expected", "case_id"),
    [
        (_dt(11), _dt(13), True, "starts-inside"),
        (_dt(9), _dt(11), True, "ends-inside"),
        (_dt(9), _dt(13), True, "contains-booking"),
        (_dt(10, 30), _dt(11, 30), True, "contained-by-booking"),
        (_dt(12), _dt(14), False, "adjacent-is-not-overlap"),
    ],
)
def test_tc55_ac4_03_interval_overlap_matrix(
    start: datetime, end: datetime, expected: bool, case_id: str
) -> None:
    del case_id
    booking_start, booking_end = _dt(10), _dt(12)

    assert intervals_overlap(booking_start, booking_end, start, end) is expected


# ------------------------------------------------------- TC-55-AC6-02


@pytest.mark.story("SCRUM-55")
def test_tc55_ac6_02_pending_request_does_not_block_availability() -> None:
    assert booking_blocks_availability("pending") is False


@pytest.mark.story("SCRUM-55")
def test_tc55_ac6_02_confirmed_request_blocks_availability() -> None:
    # Contrast case for the same status rule: only a confirmed hold blocks search.
    assert booking_blocks_availability("confirmed") is True
