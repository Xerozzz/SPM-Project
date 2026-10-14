"""SCRUM-84: Technical Support Staff add equipment to the catalogue."""

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from models.equipment import Equipment
from models.user import User
from repositories import equipment as equipment_repo

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
        "is_active": True,
    }
    stored = db.get(Equipment, uuid.UUID(created["id"]))
    assert stored is not None
    assert stored.total_quantity == 4
    assert catalogue_response.status_code == 200
    assert created in catalogue_response.json()


@pytest.mark.story("SCRUM-93")
async def test_technical_support_can_edit_equipment_and_catalogue_shows_changes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        created = (await client.post("/api/equipment", json=equipment_body())).json()
        response = await client.put(
            f"/api/equipment/{created['id']}",
            json=equipment_body(
                equipment_type="Document camera",
                description=None,
                total_quantity=2,
                location="Lecture Theatre Store",
                operational_status="Damaged",
            ),
        )
        catalogue_response = await client.get("/api/equipment")

    assert response.status_code == 200
    updated = response.json()
    assert updated == {
        "id": created["id"],
        "equipment_type": "Document camera",
        "description": None,
        "total_quantity": 2,
        "location": "Lecture Theatre Store",
        "operational_status": "Damaged",
        "is_active": True,
    }
    assert db.get(Equipment, uuid.UUID(created["id"])) is not None
    assert updated in catalogue_response.json()


@pytest.mark.story("SCRUM-93")
async def test_edit_keeps_its_own_type_and_location_combination(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        created = (await client.post("/api/equipment", json=equipment_body())).json()
        response = await client.put(
            f"/api/equipment/{created['id']}", json=equipment_body(total_quantity=3)
        )

    assert response.status_code == 200
    assert response.json()["total_quantity"] == 3


@pytest.mark.story("SCRUM-93")
async def test_edit_rejects_another_entries_type_and_location(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        first = (await client.post("/api/equipment", json=equipment_body())).json()
        second = (
            await client.post(
                "/api/equipment",
                json=equipment_body(equipment_type="Microphone", location="Audio Store"),
            )
        ).json()
        response = await client.put(f"/api/equipment/{second['id']}", json=equipment_body())

    assert response.status_code == 409
    assert response.json()["detail"] == "Equipment with this type and location already exists"
    assert first["id"] != second["id"]


@pytest.mark.story("SCRUM-93")
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("equipment_type", ""),
        ("location", None),
        ("operational_status", "Unavailable"),
        ("total_quantity", -1),
        ("total_quantity", 1.5),
    ],
)
async def test_edit_rejects_invalid_mandatory_equipment_values(
    make_user: MakeUser, make_client: MakeClient, field: str, value: object
) -> None:
    async with make_client(make_user("tech_support")) as client:
        created = (await client.post("/api/equipment", json=equipment_body())).json()
        response = await client.put(
            f"/api/equipment/{created['id']}", json=equipment_body(**{field: value})
        )

    assert response.status_code == 422
    assert field in {problem["field"] for problem in response.json()["detail"]}


@pytest.mark.story("SCRUM-93")
@pytest.mark.parametrize("role", ["organiser", "coordinator", "venue_staff", "attendee"])
async def test_non_technical_support_users_cannot_edit_equipment(
    make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    async with make_client(make_user("tech_support")) as client:
        created = (await client.post("/api/equipment", json=equipment_body())).json()

    async with make_client(make_user(role)) as client:
        response = await client.put(
            f"/api/equipment/{created['id']}", json=equipment_body(total_quantity=3)
        )

    assert response.status_code == 403


@pytest.mark.story("SCRUM-93")
async def test_missing_equipment_cannot_be_edited(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.put(f"/api/equipment/{uuid.uuid4()}", json=equipment_body())

    assert response.status_code == 404


@pytest.mark.story("SCRUM-93")
async def test_unauthenticated_users_cannot_edit_equipment(make_client: MakeClient) -> None:
    async with make_client(None) as client:
        response = await client.put(f"/api/equipment/{uuid.uuid4()}", json=equipment_body())

    assert response.status_code == 401


@pytest.mark.story("SCRUM-84")
async def test_description_is_optional(make_user: MakeUser, make_client: MakeClient) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.post("/api/equipment", json=equipment_body(description=None))

    assert response.status_code == 201
    assert response.json()["description"] is None


@pytest.mark.story("SCRUM-84")
async def test_text_at_database_column_limits_is_accepted(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.post(
            "/api/equipment",
            json=equipment_body(
                equipment_type="P" * 200,
                description="D" * 1000,
                location="L" * 200,
            ),
        )

    assert response.status_code == 201


@pytest.mark.story("SCRUM-84")
@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("equipment_type", "P" * 201, "must be 200 characters or fewer"),
        ("description", "D" * 1001, "must be 1000 characters or fewer"),
        ("location", "L" * 201, "must be 200 characters or fewer"),
    ],
)
async def test_text_over_database_column_limit_has_a_field_specific_error(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    field: str,
    value: str,
    reason: str,
) -> None:
    equipment_count_before = db.query(Equipment).count()
    async with make_client(make_user("tech_support")) as client:
        response = await client.post("/api/equipment", json=equipment_body(**{field: value}))

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": field, "reason": reason}]
    assert db.query(Equipment).count() == equipment_count_before


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
    equipment_count_before = db.query(Equipment).count()
    async with make_client(make_user("tech_support")) as client:
        response = await client.post("/api/equipment", json=equipment_body(**{field: value}))

    assert response.status_code == 422
    assert field in {problem["field"] for problem in response.json()["detail"]}
    assert db.query(Equipment).count() == equipment_count_before


@pytest.mark.story("SCRUM-84")
@pytest.mark.parametrize("quantity", [1.5, "4", True])
async def test_non_whole_number_quantities_are_rejected(
    db: Session, make_user: MakeUser, make_client: MakeClient, quantity: object
) -> None:
    equipment_count_before = db.query(Equipment).count()
    async with make_client(make_user("tech_support")) as client:
        response = await client.post("/api/equipment", json=equipment_body(total_quantity=quantity))

    assert response.status_code == 422
    assert db.query(Equipment).count() == equipment_count_before


@pytest.mark.story("SCRUM-84")
async def test_fractional_quantity_uses_the_catalogue_validation_error_shape(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.post("/api/equipment", json=equipment_body(total_quantity=1.5))

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "total_quantity", "reason": "must be a whole number"}
    ]


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
async def test_database_identity_constraint_reports_a_concurrent_duplicate(
    make_user: MakeUser, make_client: MakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repository maps only the named constraint if the friendly check misses a race."""
    async with make_client(make_user("tech_support")) as client:
        assert (await client.post("/api/equipment", json=equipment_body())).status_code == 201
        monkeypatch.setattr(
            equipment_repo,
            "get_by_type_and_location",
            lambda db, equipment_type, location: None,
        )
        response = await client.post("/api/equipment", json=equipment_body())

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


@pytest.mark.story("SCRUM-103")
async def test_technical_support_can_deactivate_equipment_without_deleting_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        created = (await client.post("/api/equipment", json=equipment_body())).json()
        deactivated = await client.post(f"/api/equipment/{created['id']}/deactivate")
        catalogue = await client.get("/api/equipment")

    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert created["id"] not in {entry["id"] for entry in catalogue.json()}
    stored = db.get(Equipment, uuid.UUID(created["id"]))
    assert stored is not None
    assert stored.is_active is False
    assert stored.operational_status == "Operational"


@pytest.mark.story("SCRUM-103")
@pytest.mark.parametrize("role", ["organiser", "coordinator", "venue_staff", "attendee"])
async def test_non_technical_support_users_cannot_deactivate_equipment(
    make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    async with make_client(make_user(role)) as client:
        response = await client.post(f"/api/equipment/{uuid.uuid4()}/deactivate")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-103")
async def test_deactivating_unknown_equipment_is_not_found(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("tech_support")) as client:
        response = await client.post(f"/api/equipment/{uuid.uuid4()}/deactivate")

    assert response.status_code == 404
