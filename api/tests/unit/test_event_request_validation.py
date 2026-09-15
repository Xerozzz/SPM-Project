"""SCRUM-46 (F2): what "complete and valid" means for submission, one rule per test."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from domain.event_request import (
    REQUIRED_TEXT_FIELDS,
    EQUIPMENT_REQUIREMENTS,
    EventRequestFields,
    FieldProblem,
    VENUE_REQUIREMENTS,
    field_names,
    validate_catalogue_requirements,
    validate_event_request,
)

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


def complete_request() -> EventRequestFields:
    return EventRequestFields(
        name="Orientation Day",
        purpose="Welcome new students",
        description="Half-day programme with talks and a campus tour.",
        start_at=NOW + timedelta(days=30),
        end_at=NOW + timedelta(days=30, hours=4),
        expected_attendance=200,
        venue_requirement="Auditorium-type venue",
        accessibility_requirement="Step-free access and hearing loop",
        equipment_requirement="Projector-type requirement",
        layout_requirement="Theatre style",
        registration_requirement="Open registration, capped at 200",
    )


def problem_fields(problems: list[FieldProblem]) -> list[str]:
    return [p.field for p in problems]


@pytest.mark.story("SCRUM-46")
def test_a_complete_request_has_no_problems() -> None:
    assert validate_event_request(complete_request(), NOW) == []


@pytest.mark.story("SCRUM-46")
@pytest.mark.parametrize("field", REQUIRED_TEXT_FIELDS)
def test_each_missing_text_field_is_named(field: str) -> None:
    missing: dict[str, Any] = {field: None}
    request = replace(complete_request(), **missing)

    assert validate_event_request(request, NOW) == [FieldProblem(field, "is required")]


@pytest.mark.story("SCRUM-46")
@pytest.mark.parametrize("field", REQUIRED_TEXT_FIELDS)
def test_whitespace_only_text_counts_as_missing(field: str) -> None:
    blank: dict[str, Any] = {field: "   "}
    request = replace(complete_request(), **blank)

    assert problem_fields(validate_event_request(request, NOW)) == [field]


@pytest.mark.story("SCRUM-46")
def test_every_missing_field_is_reported_at_once() -> None:
    # AC2: the organiser is shown *which fields* need correcting — all of them, in one go.
    problems = validate_event_request(EventRequestFields(), NOW)

    assert problem_fields(problems) == [
        *REQUIRED_TEXT_FIELDS,
        "start_at",
        "end_at",
        "expected_attendance",
    ]


@pytest.mark.story("SCRUM-46")
def test_start_must_be_in_the_future() -> None:
    request = replace(complete_request(), start_at=NOW, end_at=NOW + timedelta(hours=1))

    assert validate_event_request(request, NOW) == [
        FieldProblem("start_at", "must be in the future")
    ]


@pytest.mark.story("SCRUM-46")
def test_end_must_be_after_start() -> None:
    start = NOW + timedelta(days=1)
    request = replace(complete_request(), start_at=start, end_at=start)

    assert validate_event_request(request, NOW) == [
        FieldProblem("end_at", "must be after the start")
    ]


@pytest.mark.story("SCRUM-46")
def test_end_before_start_is_reported_on_end() -> None:
    start = NOW + timedelta(days=1)
    request = replace(complete_request(), start_at=start, end_at=start - timedelta(hours=1))

    assert problem_fields(validate_event_request(request, NOW)) == ["end_at"]


@pytest.mark.story("SCRUM-46")
def test_naive_datetimes_are_rejected_on_both_ends() -> None:
    # AGENTS.md §3: a datetime without a timezone is a bug, not a value.
    naive = (NOW + timedelta(days=80)).replace(tzinfo=None)
    request = replace(complete_request(), start_at=naive, end_at=naive)

    assert validate_event_request(request, NOW) == [
        FieldProblem("start_at", "must include a timezone"),
        FieldProblem("end_at", "must include a timezone"),
    ]


@pytest.mark.story("SCRUM-46")
def test_end_is_not_compared_against_a_naive_start() -> None:
    naive = (NOW + timedelta(days=80)).replace(tzinfo=None)
    request = replace(complete_request(), start_at=naive)

    # Only the start is wrong; end_at is aware and cannot be meaningfully compared to it.
    assert problem_fields(validate_event_request(request, NOW)) == ["start_at"]


@pytest.mark.story("SCRUM-46")
@pytest.mark.parametrize("attendance", [0, -5])
def test_expected_attendance_must_be_positive(attendance: int) -> None:
    request = replace(complete_request(), expected_attendance=attendance)

    assert validate_event_request(request, NOW) == [
        FieldProblem("expected_attendance", "must be a positive number")
    ]


@pytest.mark.story("SCRUM-46")
def test_missing_attendance_is_required_not_invalid() -> None:
    request = replace(complete_request(), expected_attendance=None)

    assert validate_event_request(request, NOW) == [
        FieldProblem("expected_attendance", "is required")
    ]


@pytest.mark.story("SCRUM-28")
def test_catalogue_requirements_accept_the_temporary_options() -> None:
    request = complete_request()

    assert request.venue_requirement in VENUE_REQUIREMENTS
    assert request.equipment_requirement in EQUIPMENT_REQUIREMENTS
    assert validate_catalogue_requirements(request) == []


@pytest.mark.story("SCRUM-28")
def test_catalogue_requirements_reject_unknown_values_but_allow_empty_draft_fields() -> None:
    invalid = replace(
        EventRequestFields(),
        venue_requirement="A room chosen by the organiser",
        equipment_requirement="Any available projector",
    )

    assert validate_catalogue_requirements(invalid) == [
        FieldProblem("venue_requirement", "is not a catalogue option"),
        FieldProblem("equipment_requirement", "is not a catalogue option"),
    ]
    assert validate_catalogue_requirements(EventRequestFields()) == []


@pytest.mark.story("SCRUM-46")
def test_field_names_cover_the_whole_ticket_in_order() -> None:
    assert field_names() == (
        "name",
        "purpose",
        "description",
        "start_at",
        "end_at",
        "expected_attendance",
        "venue_requirement",
        "accessibility_requirement",
        "equipment_requirement",
        "layout_requirement",
        "registration_requirement",
    )
