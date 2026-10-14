"""SCRUM-104: organisers select venue requirements from the active catalogue."""

from collections.abc import Callable
from datetime import time

import httpx
import pytest
from sqlalchemy.orm import Session

from models.equipment import Equipment
from models.user import User
from models.venue import Venue

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]
_VENUE_NAME = "Venue Catalogue Test Hall"


def add_catalogue_entries(db: Session) -> Venue:
    venue = db.query(Venue).filter(Venue.name == _VENUE_NAME).first()
    if venue is None:
        venue = Venue(
            name=_VENUE_NAME,
            location="Level 2",
            maximum_capacity=200,
            facilities=[],
            supported_layouts=[],
            accessibility_features=[],
            opens_at=time(8),
            closes_at=time(22),
        )
        db.add(venue)
    else:
        venue.is_active = True
    if (
        db.query(Equipment)
        .filter(Equipment.equipment_type == "Projector", Equipment.location == "Store")
        .first()
        is None
    ):
        db.add(
            Equipment(
                equipment_type="Projector",
                description=None,
                total_quantity=1,
                location="Store",
                operational_status="Operational",
            )
        )
    db.flush()
    return venue


def request_body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "name": "Orientation Day",
        "purpose": "Welcome new students",
        "description": "Talks and tours.",
        "start_at": "2026-12-01T09:00:00+08:00",
        "end_at": "2026-12-01T13:00:00+08:00",
        "expected_attendance": 200,
        "venue_requirement": _VENUE_NAME,
        "accessibility_requirement": "Step-free access",
        "equipment_requirement": "Projector",
        "layout_requirement": "Theatre style",
        "registration_requirement": "Open registration",
    }
    values.update(overrides)
    return values


@pytest.mark.story("SCRUM-28")
async def test_organiser_sees_active_venue_names_in_catalogue_order(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    add_catalogue_entries(db)
    db.add(
        Venue(
            name="Atrium",
            location="Level 1",
            maximum_capacity=100,
            facilities=[],
            supported_layouts=[],
            accessibility_features=[],
            opens_at=time(8),
            closes_at=time(22),
        )
    )
    db.flush()

    async with make_client(make_user("organiser")) as client:
        response = await client.get("/api/event-requests/venue-names")

    assert response.status_code == 200
    names = response.json()
    assert names == sorted(names)
    assert "Atrium" in names
    assert _VENUE_NAME in names


@pytest.mark.story("SCRUM-28")
async def test_event_request_rejects_venue_not_in_active_catalogue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    add_catalogue_entries(db)

    async with make_client(make_user("organiser")) as client:
        response = await client.post(
            "/api/event-requests", json=request_body(venue_requirement="Unknown hall")
        )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "venue_requirement", "reason": "is not a catalogue option"}
    ]


@pytest.mark.story("SCRUM-28")
async def test_deactivated_venue_is_not_selectable_or_accepted(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = add_catalogue_entries(db)
    venue.is_active = False
    db.flush()

    async with make_client(make_user("organiser")) as client:
        listed = await client.get("/api/event-requests/venue-names")
        created = await client.post("/api/event-requests", json=request_body())

    assert _VENUE_NAME not in listed.json()
    assert created.status_code == 422
    assert created.json()["detail"] == [
        {"field": "venue_requirement", "reason": "is not a catalogue option"}
    ]
