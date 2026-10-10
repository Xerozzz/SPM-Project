"""SCRUM-84: Technical Support Staff add equipment to the catalogue."""

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from models.equipment import Equipment
from models.user import User

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def equipment_body(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "equipment_type": "Projector",
        "description": "Portable presentation projector",
        "total_quantity": 4,
        "location": "Media Store",
        "operational_status": "Operational",
    }
    values.update(overrides)
    return values


@pytest.mark.story("SCRUM-84")
async def test_technical_support_can_create_and_view_equipment(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        created_response = await client.post("/api/equipment", json=equipment_body())
        catalogue_response = await client.get("/api/equipment")

    assert created_response.status_code == 201
    created = created_response.json()
    assert created == {
        "id": created["id"],
        "equipment_type": "Projector",
        "description": "Portable presentation projector",
        "total_quantity": 4,
        "location": "Media Store",
        "operational_status": "Operational",
    }
    stored = db.get(Equipment, uuid.UUID(created["id"]))
    assert stored is not None
    assert stored.total_quantity == 4
    assert catalogue_response.status_code == 200
    assert catalogue_response.json() == [created]


@pytest.mark.story("SCRUM-84")
async def test_description_is_optional(make_user: MakeUser, make_client: MakeClient) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.post("/api/equipment", json=equipment_body(description=None))

    assert response.status_code == 201
    assert response.json()["description"] is None


@pytest.mark.story("SCRUM-84")
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("equipment_type", None),
        ("location", ""),
        ("operational_status", "   "),
        ("operational_status", "Unavailable"),
        ("total_quantity", None),
        ("total_quantity", -1),
    ],
)
async def test_missing_or_invalid_mandatory_equipment_is_not_saved(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    field: str,
    value: object,
) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.post("/api/equipment", json=equipment_body(**{field: value}))

    assert response.status_code == 422
    assert field in {problem["field"] for problem in response.json()["detail"]}
    assert db.query(Equipment).count() == 0


@pytest.mark.story("SCRUM-84")
@pytest.mark.parametrize("quantity", [1.5, "4", True])
async def test_non_whole_number_quantities_are_rejected(
    db: Session, make_user: MakeUser, make_client: MakeClient, quantity: object
) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.post("/api/equipment", json=equipment_body(total_quantity=quantity))

    assert response.status_code == 422
    assert db.query(Equipment).count() == 0


@pytest.mark.story("SCRUM-84")
async def test_duplicate_equipment_type_and_location_is_rejected(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        assert (await client.post("/api/equipment", json=equipment_body())).status_code == 201
        response = await client.post(
            "/api/equipment", json=equipment_body(description="A duplicate record")
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Equipment with this type and location already exists"


@pytest.mark.story("SCRUM-84")
@pytest.mark.parametrize("role", ["organiser", "coordinator", "venue_staff", "attendee"])
async def test_non_technical_support_users_cannot_create_equipment(
    make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    async with make_client(make_user(role)) as client:
        response = await client.post("/api/equipment", json=equipment_body())

    assert response.status_code == 403


@pytest.mark.story("SCRUM-84")
async def test_unauthenticated_users_cannot_create_equipment(make_client: MakeClient) -> None:
    async with make_client(None) as client:
        response = await client.post("/api/equipment", json=equipment_body())

    assert response.status_code == 401
