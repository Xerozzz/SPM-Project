"""Focused SCRUM-38 service checks for venue booking submission helpers."""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import cast

import pytest
from sqlalchemy.orm import Session

from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from models.venue import Venue
from repositories import equipment_requirements as requirement_repo
from repositories import venues as venue_repo
from services import venue_bookings


def _event(**overrides: object) -> EventRequest:
    start = datetime(2030, 1, 1, 10, tzinfo=UTC)
    values: dict[str, object] = {
        "name": "Orientation Day",
        "purpose": "Welcome new students",
        "description": "Half-day programme",
        "start_at": start,
        "end_at": start + timedelta(hours=2),
        "expected_attendance": 50,
        "venue_requirement": "Hall A",
        "accessibility_requirement": "Step-free access",
        "equipment_requirement": "Display screen",
        "layout_requirement": "Theatre style",
        "registration_requirement": "Open registration",
    }
    values.update(overrides)
    return EventRequest(**values)


def _venue(**overrides: object) -> Venue:
    values: dict[str, object] = {
        "name": "Hall A",
        "location": "Level 2",
        "maximum_capacity": 100,
        "facilities": [],
        "accessibility_features": [],
        "supported_layouts": [],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
        "is_active": True,
    }
    values.update(overrides)
    return Venue(**values)


def _requires(monkeypatch: pytest.MonkeyPatch, *types: str) -> None:
    """The event's maintained requirements, as SCRUM-43 keeps them."""
    rows = [EventEquipmentRequirement(equipment_type=t, quantity=1) for t in types]
    monkeypatch.setattr(requirement_repo, "list_for_event", lambda _db, _event_id: rows)


@pytest.mark.story("SCRUM-38")
def test_evaluate_uses_explicit_equipment_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    venue_id = uuid.uuid4()

    def get_venue(_db: Session, requested_id: uuid.UUID) -> Venue | None:
        assert requested_id == venue_id
        return _venue()

    monkeypatch.setattr(venue_repo, "get", get_venue)
    _requires(monkeypatch, "Display screen")

    result = venue_bookings.evaluate(
        cast(Session, object()), _event(), venue_id, datetime(2029, 1, 1, tzinfo=UTC)
    )

    assert result.unavailable_facilities == ["Display screen"]


@pytest.mark.story("SCRUM-43")
def test_evaluate_judges_every_maintained_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reason for the change: an event needing three things was judged on one.

    `equipment_requirement` holds a single type, so suitability only ever asked about one
    of them however many the Coordinator had recorded.
    """
    monkeypatch.setattr(venue_repo, "get", lambda _db, _venue_id: _venue())
    _requires(monkeypatch, "Display screen", "Microphone", "PA system")

    result = venue_bookings.evaluate(
        cast(Session, object()), _event(), uuid.uuid4(), datetime(2029, 1, 1, tzinfo=UTC)
    )

    assert result.unavailable_facilities == ["Display screen", "Microphone", "PA system"]


@pytest.mark.story("SCRUM-43")
def test_evaluate_ignores_the_organisers_stale_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-0033: the Coordinator does not write back to the organiser's column.

    Once a requirement is removed, the string still names it. Scoring the venue on it
    would warn about something nobody needs any more.
    """
    monkeypatch.setattr(venue_repo, "get", lambda _db, _venue_id: _venue())
    _requires(monkeypatch)  # the Coordinator removed everything

    result = venue_bookings.evaluate(
        cast(Session, object()),
        _event(equipment_requirement="Display screen"),
        uuid.uuid4(),
        datetime(2029, 1, 1, tzinfo=UTC),
    )

    assert result.unavailable_facilities == []


@pytest.mark.story("SCRUM-43")
def test_a_requirement_with_no_venue_counterpart_is_not_a_missing_facility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Equipment types and venue facilities are separate vocabularies (ADR-0031/0032).

    A venue offers a fixed projector; it does not offer the portable things that arrive
    from the store room. Reporting one as a facility the venue lacks would warn about
    every venue, every time.
    """
    monkeypatch.setattr(venue_repo, "get", lambda _db, _venue_id: _venue())
    _requires(monkeypatch, "Smoke machine", "Display screen")

    result = venue_bookings.evaluate(
        cast(Session, object()), _event(), uuid.uuid4(), datetime(2029, 1, 1, tzinfo=UTC)
    )

    assert result.unavailable_facilities == ["Display screen"]


@pytest.mark.story("SCRUM-38")
def test_evaluate_reports_event_and_missing_venue_problems(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(venue_repo, "get", lambda _db, _venue_id: None)

    with pytest.raises(venue_bookings.InvalidBookingRequestError) as exc_info:
        venue_bookings.evaluate(
            cast(Session, object()),
            _event(expected_attendance=None),
            uuid.uuid4(),
            datetime(2029, 1, 1, tzinfo=UTC),
        )

    assert [(problem.field, problem.reason) for problem in exc_info.value.problems] == [
        ("expected_attendance", "is required"),
        ("venue_id", "does not identify a venue"),
    ]
