"""SCRUM-56: venue suitability check.

Covers all Unit cases from `SCRUM-56 TC.csv`:
AC1 (capacity): TC-56-AC1-01/02/03
AC2 (facilities): TC-56-AC2-01/02/03
AC3 (accessibility display): TC-56-AC3-01/02
AC4 (layout display): TC-56-AC4-01/02
AC5 (happy path): TC-56-AC5-01
Cross-criterion: TC-56-AC1-AC2-01, TC-56-AC3-AC4-01

Contract under test (`domain/venue_suitability.py`):
  SuitabilityEvent(expected_attendance, required_facilities,
                   accessibility_need=None, layout_need=None)
  SuitabilityVenue(maximum_capacity, facilities,
                   accessibility_features, supported_layouts)
  evaluate_suitability(event, venue) -> SuitabilityResult with:
    mismatch_codes: list[str]  # contains "CAPACITY_EXCEEDED" on overflow
    expected_attendance: int
    venue_capacity: int
    unavailable_facilities: list[str]
    accessibility_need: str | None  # what was asked for, echoed for display
    venue_accessibility: list[str]  # venue's recorded features, for display
    layout_need: str | None         # what was asked for, echoed for display
    venue_layouts: list[str]        # venue's supported layouts, for display

Accessibility/layout needs never auto-reject: the evaluator returns the need
paired with the venue data for the Coordinator to assess (AC3/AC4 remarks).
"""

from typing import Any

import pytest

from domain.venue import ROOM_LAYOUTS
from domain.venue_suitability import (
    SuitabilityEvent,
    SuitabilityVenue,
    evaluate_suitability,
)


def make_event(**overrides: Any) -> SuitabilityEvent:
    values: dict[str, Any] = {
        "expected_attendance": 120,
        "required_facilities": [],
        "accessibility_need": None,
        "layout_need": None,
    }
    values.update(overrides)
    return SuitabilityEvent(**values)


def make_venue(**overrides: Any) -> SuitabilityVenue:
    values: dict[str, Any] = {
        "maximum_capacity": 200,
        "facilities": [],
        "accessibility_features": [],
        "supported_layouts": [],
    }
    values.update(overrides)
    return SuitabilityVenue(**values)


# ------------------------------------------------------------------ AC1: capacity


@pytest.mark.story("SCRUM-56")
def test_tc56_ac1_01_attendance_above_capacity_is_mismatch() -> None:
    event = make_event(expected_attendance=201)
    venue = make_venue(maximum_capacity=200)

    result = evaluate_suitability(event, venue)

    assert "CAPACITY_EXCEEDED" in result.mismatch_codes
    assert result.expected_attendance == 201
    assert result.venue_capacity == 200


@pytest.mark.story("SCRUM-56")
def test_tc56_ac1_02_attendance_equal_to_capacity_is_not_mismatch() -> None:
    event = make_event(expected_attendance=200)
    venue = make_venue(maximum_capacity=200)

    result = evaluate_suitability(event, venue)

    assert "CAPACITY_EXCEEDED" not in result.mismatch_codes


@pytest.mark.story("SCRUM-56")
def test_tc56_ac1_03_attendance_below_capacity_is_not_mismatch() -> None:
    event = make_event(expected_attendance=120)
    venue = make_venue(maximum_capacity=200)

    result = evaluate_suitability(event, venue)

    assert "CAPACITY_EXCEEDED" not in result.mismatch_codes


# ------------------------------------------------------------------ AC2: facilities


@pytest.mark.story("SCRUM-56")
def test_tc56_ac2_01_missing_facility_is_listed() -> None:
    event = make_event(required_facilities=["Projector"])
    venue = make_venue(facilities=["Whiteboard", "PA system"])

    result = evaluate_suitability(event, venue)

    assert result.unavailable_facilities == ["Projector"]


@pytest.mark.story("SCRUM-56")
def test_tc56_ac2_02_available_facility_leaves_list_empty() -> None:
    event = make_event(required_facilities=["Projector"])
    venue = make_venue(facilities=["Projector", "Whiteboard"])

    result = evaluate_suitability(event, venue)

    assert result.unavailable_facilities == []


@pytest.mark.story("SCRUM-56")
def test_tc56_ac2_03_only_missing_facilities_are_listed() -> None:
    event = make_event(required_facilities=["Projector", "Whiteboard", "PA system"])
    venue = make_venue(facilities=["Projector"])

    result = evaluate_suitability(event, venue)

    assert result.unavailable_facilities == ["Whiteboard", "PA system"]


@pytest.mark.story("SCRUM-56")
def test_tc56_ac2_04_facility_matching_ignores_case_and_whitespace() -> None:
    event = make_event(required_facilities=["projector", "  PA SYSTEM  "])
    venue = make_venue(facilities=["Projector", "PA system"])

    result = evaluate_suitability(event, venue)

    assert result.unavailable_facilities == []


@pytest.mark.story("SCRUM-56")
def test_tc56_ac2_05_duplicated_requirement_is_reported_once() -> None:
    event = make_event(required_facilities=["Projector", "Projector"])
    venue = make_venue(facilities=["Whiteboard"])

    result = evaluate_suitability(event, venue)

    assert result.unavailable_facilities == ["Projector"]


# ------------------------------------------------------------------ AC3: accessibility display


@pytest.mark.story("SCRUM-56")
def test_tc56_ac3_01_matching_accessibility_returns_venue_features() -> None:
    event = make_event(accessibility_need="Step-free access")
    venue = make_venue(accessibility_features=["Step-free access", "Hearing loop"])

    result = evaluate_suitability(event, venue)

    assert result.accessibility_need == "Step-free access"
    assert result.venue_accessibility == ["Step-free access", "Hearing loop"]


@pytest.mark.story("SCRUM-56")
def test_tc56_ac3_02_absent_need_still_returns_venue_features_without_reject() -> None:
    event = make_event(accessibility_need="Wheelchair ramp")
    venue = make_venue(accessibility_features=["Hearing loop"])

    result = evaluate_suitability(event, venue)

    assert result.accessibility_need == "Wheelchair ramp"
    assert result.venue_accessibility == ["Hearing loop"]
    assert "CAPACITY_EXCEEDED" not in result.mismatch_codes


# ------------------------------------------------------------------ AC4: layout display


@pytest.mark.story("SCRUM-56")
def test_tc56_ac4_01_supported_layout_returns_venue_layouts() -> None:
    assert "theatre" in ROOM_LAYOUTS and "classroom" in ROOM_LAYOUTS
    event = make_event(layout_need="theatre")
    venue = make_venue(supported_layouts=["theatre", "classroom"])

    result = evaluate_suitability(event, venue)

    assert result.layout_need == "theatre"
    assert result.venue_layouts == ["theatre", "classroom"]


@pytest.mark.story("SCRUM-56")
def test_tc56_ac4_02_unsupported_layout_still_returns_venue_layouts_without_reject() -> None:
    assert "theatre" in ROOM_LAYOUTS and "classroom" in ROOM_LAYOUTS
    event = make_event(layout_need="banquet")
    venue = make_venue(supported_layouts=["classroom"])

    result = evaluate_suitability(event, venue)

    assert result.layout_need == "banquet"
    assert result.venue_layouts == ["classroom"]
    assert "CAPACITY_EXCEEDED" not in result.mismatch_codes


# ------------------------------------------------------------------ AC5: happy path


@pytest.mark.story("SCRUM-56")
def test_tc56_ac5_01_fitting_capacity_and_facility_has_no_warnings() -> None:
    event = make_event(expected_attendance=120, required_facilities=["Projector"])
    venue = make_venue(maximum_capacity=200, facilities=["Projector"])

    result = evaluate_suitability(event, venue)

    assert "CAPACITY_EXCEEDED" not in result.mismatch_codes
    assert result.unavailable_facilities == []


# ------------------------------------------------------------------ cross-criterion


@pytest.mark.story("SCRUM-56")
def test_tc56_ac1_ac2_01_capacity_and_facility_issues_reported_together() -> None:
    event = make_event(expected_attendance=250, required_facilities=["Projector", "PA system"])
    venue = make_venue(maximum_capacity=200, facilities=["Projector"])

    result = evaluate_suitability(event, venue)

    assert "CAPACITY_EXCEEDED" in result.mismatch_codes
    assert result.unavailable_facilities == ["PA system"]


@pytest.mark.story("SCRUM-56")
def test_tc56_ac3_ac4_01_absent_optional_needs_succeed_without_warnings() -> None:
    event = make_event(accessibility_need=None, layout_need=None)
    venue = make_venue(
        accessibility_features=["Step-free access"],
        supported_layouts=["theatre"],
    )

    result = evaluate_suitability(event, venue)

    assert "CAPACITY_EXCEEDED" not in result.mismatch_codes
    assert result.unavailable_facilities == []
    assert result.accessibility_need is None
    assert result.venue_accessibility == ["Step-free access"]
    assert result.layout_need is None
    assert result.venue_layouts == ["theatre"]
