"""Focused SCRUM-38 service checks for venue booking submission helpers."""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import cast

import pytest
from sqlalchemy.orm import Session

from models.event_request import EventRequest
from models.venue import Venue
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
        "venue_requirement": "Auditorium-type venue",
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


@pytest.mark.story("SCRUM-38")
def test_evaluate_uses_explicit_equipment_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    venue_id = uuid.uuid4()

    def get_venue(_db: Session, requested_id: uuid.UUID) -> Venue | None:
        assert requested_id == venue_id
        return _venue()

    monkeypatch.setattr(venue_repo, "get", get_venue)

    result = venue_bookings.evaluate(
        cast(Session, object()), _event(), venue_id, datetime(2029, 1, 1, tzinfo=UTC)
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
