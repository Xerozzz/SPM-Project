"""SCRUM-90: organisers select equipment requirements from the catalogue."""

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from models.equipment import Equipment
from models.user import User

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def add_equipment(db: Session, equipment_type: str, location: str) -> None:
    db.add(
        Equipment(
            equipment_type=equipment_type,
            description=None,
            total_quantity=1,
            location=location,
            operational_status="Operational",
            created_at=datetime.now(UTC),
        )
    )
    db.flush()


def request_body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "name": "Orientation Day",
        "purpose": "Welcome new students",
        "description": "Talks and campus tours.",
        "start_at": "2026-12-01T09:00:00+08:00",
        "end_at": "2026-12-01T13:00:00+08:00",
        "expected_attendance": 200,
        "venue_requirement": "Auditorium-type venue",
        "accessibility_requirement": "Step-free access",
        "equipment_requirement": "Projector",
        "layout_requirement": "Theatre style",
        "registration_requirement": "Open registration",
    }
    values.update(overrides)
    return values


@pytest.mark.story("SCRUM-90")
async def test_organiser_sees_distinct_catalogue_equipment_types(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    add_equipment(db, "Projector", "Media Store")
    add_equipment(db, "Projector", "Lecture Theatre Store")
    add_equipment(db, "Microphone", "Audio Store")

    async with make_client(make_user("organiser")) as client:
        response = await client.get("/api/event-requests/equipment-types")

    assert response.status_code == 200
    equipment_types = response.json()
    assert equipment_types == sorted(equipment_types)
    assert equipment_types.count("Microphone") == 1
    assert equipment_types.count("Projector") == 1


@pytest.mark.story("SCRUM-90")
async def test_only_an_organiser_can_read_equipment_requirement_types(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("coordinator")) as client:
        response = await client.get("/api/event-requests/equipment-types")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-90")
async def test_event_request_rejects_equipment_not_in_catalogue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    add_equipment(db, "Projector", "Media Store")

    async with make_client(make_user("organiser")) as client:
        response = await client.post(
            "/api/event-requests", json=request_body(equipment_requirement="Microphone")
        )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "equipment_requirement", "reason": "is not a catalogue option"}
    ]


@pytest.mark.story("SCRUM-90")
async def test_event_request_accepts_an_equipment_type_from_catalogue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    add_equipment(db, "Projector", "Media Store")

    async with make_client(make_user("organiser")) as client:
        response = await client.post("/api/event-requests", json=request_body())

    assert response.status_code == 201
    assert response.json()["equipment_requirement"] == "Projector"
