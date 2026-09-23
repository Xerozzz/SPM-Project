"""SCRUM-59: reading the venue catalogue and adding to it.

Venue Staff add venues (AC1) and everyone signed in reads them (AC2). Invalid data is
refused with the affected field named and nothing stored (AC5). A deactivated venue leaves
the selectable list but stays readable by id (AC3, AC4), which is what soft deactivation
buys (ADR-0012); the endpoint that deactivates one lands with the story that adds it, so
deactivating one is now an endpoint too.
"""

import uuid
from collections.abc import Callable
from datetime import time
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from models.user import User
from models.venue import Venue

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def venue_body(**overrides: Any) -> dict[str, Any]:
    """A complete, valid venue payload; pass field=value to change or break one."""
    values: dict[str, Any] = {
        "name": "Hall A",
        "location": "Level 2, School of Computing",
        "maximum_capacity": 200,
        "facilities": ["Projector", "Hearing loop"],
        "supported_layouts": ["theatre", "classroom"],
        "accessibility_features": ["Step-free access"],
        "opens_at": "08:00:00",
        "closes_at": "22:00:00",
    }
    values.update(overrides)
    return values


async def create_venue(client: httpx.AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/api/venues", json=venue_body(**overrides))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def make_venue(db: Session, **overrides: Any) -> Venue:
    """A complete venue; pass field=value to change one."""
    values: dict[str, Any] = {
        "name": "Hall A",
        "location": "Level 2, School of Computing",
        "maximum_capacity": 200,
        "facilities": ["Projector", "Hearing loop"],
        "supported_layouts": ["theatre", "classroom"],
        "accessibility_features": ["Step-free access"],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
    }
    values.update(overrides)
    venue = Venue(**values)
    db.add(venue)
    db.flush()
    return venue


@pytest.mark.story("SCRUM-59")
async def test_a_coordinator_can_view_the_catalogue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)

    async with make_client(make_user("coordinator")) as client:
        response = await client.get("/api/venues")

    assert response.status_code == 200
    body = response.json()
    assert [row["name"] for row in body] == ["Hall A"]
    # Every attribute AC1 names is on the wire, so a coordinator can judge suitability.
    assert body[0]["id"] == str(venue.id)
    assert body[0]["location"] == "Level 2, School of Computing"
    assert body[0]["maximum_capacity"] == 200
    assert body[0]["facilities"] == ["Projector", "Hearing loop"]
    assert body[0]["supported_layouts"] == ["theatre", "classroom"]
    assert body[0]["accessibility_features"] == ["Step-free access"]
    assert body[0]["opens_at"] == "08:00:00"
    assert body[0]["closes_at"] == "22:00:00"


@pytest.mark.story("SCRUM-59")
async def test_the_catalogue_is_listed_by_name(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Seminar Room")
    make_venue(db, name="Auditorium")

    async with make_client(make_user("coordinator")) as client:
        response = await client.get("/api/venues")

    assert [row["name"] for row in response.json()] == ["Auditorium", "Seminar Room"]


@pytest.mark.story("SCRUM-59")
async def test_a_deactivated_venue_is_not_in_the_selectable_catalogue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    make_venue(db, name="Hall A")
    make_venue(db, name="Old Sports Hall", is_active=False)

    async with make_client(make_user("coordinator")) as client:
        response = await client.get("/api/venues")

    assert [row["name"] for row in response.json()] == ["Hall A"]


@pytest.mark.story("SCRUM-59")
async def test_a_deactivated_venue_is_still_readable_by_id(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC4: an event or booking that already names this venue keeps a readable record.
    venue = make_venue(db, is_active=False)

    async with make_client(make_user("coordinator")) as client:
        response = await client.get(f"/api/venues/{venue.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Hall A"
    assert response.json()["location"] == "Level 2, School of Computing"
    assert response.json()["maximum_capacity"] == 200
    assert response.json()["is_active"] is False


@pytest.mark.story("SCRUM-59")
async def test_an_unknown_venue_is_not_found(make_user: MakeUser, make_client: MakeClient) -> None:
    async with make_client(make_user("coordinator")) as client:
        response = await client.get(f"/api/venues/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.story("SCRUM-59")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "venue_staff"])
async def test_every_signed_in_role_may_read_the_catalogue(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    # The catalogue is reference data for planning, not something to hide from a role.
    make_venue(db)

    async with make_client(make_user(role)) as client:
        response = await client.get("/api/venues")

    assert response.status_code == 200


@pytest.mark.story("SCRUM-59")
async def test_the_catalogue_requires_a_signed_in_user(make_client: MakeClient) -> None:
    async with make_client(None) as anonymous:
        assert (await anonymous.get("/api/venues")).status_code == 401
        assert (await anonymous.get(f"/api/venues/{uuid.uuid4()}")).status_code == 401


# ------------------------------------------------- AC1 and AC5: adding a venue


@pytest.mark.story("SCRUM-59")
async def test_venue_staff_create_a_venue_with_every_attribute(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post("/api/venues", json=venue_body())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Hall A"
    assert body["location"] == "Level 2, School of Computing"
    assert body["maximum_capacity"] == 200
    assert body["facilities"] == ["Projector", "Hearing loop"]
    assert body["supported_layouts"] == ["theatre", "classroom"]
    assert body["accessibility_features"] == ["Step-free access"]
    assert body["opens_at"] == "08:00:00"
    assert body["closes_at"] == "22:00:00"
    # A new venue is selectable straight away; nothing else has to happen to it.
    assert body["is_active"] is True

    stored = db.get(Venue, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.name == "Hall A"


@pytest.mark.story("SCRUM-59")
async def test_a_duplicate_venue_name_is_refused(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        await create_venue(client)
        response = await client.post("/api/venues", json=venue_body(location="Elsewhere"))

    assert response.status_code == 409
    assert response.json()["detail"] == "A venue with that name already exists"


@pytest.mark.story("SCRUM-59")
async def test_a_coordinator_cannot_add_a_venue(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC2: a coordinator views the catalogue but does not maintain it.
    async with make_client(make_user("coordinator")) as coordinator:
        response = await coordinator.post("/api/venues", json=venue_body())

    assert response.status_code == 403


@pytest.mark.story("SCRUM-59")
async def test_an_incomplete_venue_is_refused_and_the_fields_are_named(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    incomplete = venue_body(name=None, maximum_capacity=None, supported_layouts=[])

    async with make_client(make_user("venue_staff")) as client:
        response = await client.post("/api/venues", json=incomplete)

    assert response.status_code == 422
    named = {problem["field"] for problem in response.json()["detail"]}
    assert named == {"name", "maximum_capacity", "supported_layouts"}
    assert db.query(Venue).count() == 0


@pytest.mark.story("SCRUM-59")
async def test_an_invalid_venue_is_refused_with_the_reason(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(
            "/api/venues", json=venue_body(opens_at="18:00:00", closes_at="09:00:00")
        )

    assert response.status_code == 422
    problems = response.json()["detail"]
    assert [problem["field"] for problem in problems] == ["closes_at"]
    assert problems[0]["reason"] == "must be after the opening time"


@pytest.mark.story("SCRUM-59")
async def test_stored_text_is_trimmed(make_user: MakeUser, make_client: MakeClient) -> None:
    # Leading and trailing spaces are a typing artefact, not part of the venue's name.
    async with make_client(make_user("venue_staff")) as client:
        created = await create_venue(client, name="  Hall C  ", location="  Level 3  ")

    assert created["name"] == "Hall C"
    assert created["location"] == "Level 3"


# ------------------------------- AC1 update and AC3: changing and retiring a venue


@pytest.mark.story("SCRUM-59")
async def test_venue_staff_update_a_venue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        created = await create_venue(client)
        response = await client.patch(
            f"/api/venues/{created['id']}",
            json={"maximum_capacity": 250, "facilities": ["Projector", "Lectern"]},
        )

    assert response.status_code == 200
    assert response.json()["maximum_capacity"] == 250
    assert response.json()["facilities"] == ["Projector", "Lectern"]
    # Untouched fields keep their values.
    assert response.json()["name"] == "Hall A"

    db.expire_all()
    stored = db.get(Venue, uuid.UUID(created["id"]))
    assert stored is not None
    assert stored.maximum_capacity == 250


@pytest.mark.story("SCRUM-59")
async def test_a_venue_keeps_its_own_name_when_updated(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    # Re-saving a venue without changing its name must not collide with itself.
    async with make_client(make_user("venue_staff")) as client:
        created = await create_venue(client)
        response = await client.patch(
            f"/api/venues/{created['id']}", json={"name": "Hall A", "maximum_capacity": 150}
        )

    assert response.status_code == 200
    assert response.json()["maximum_capacity"] == 150


@pytest.mark.story("SCRUM-59")
async def test_a_deactivated_venue_leaves_the_selectable_catalogue(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as staff:
        keep = await create_venue(staff, name="Hall A")
        retire = await create_venue(staff, name="Hall B")
        deactivated = await staff.post(f"/api/venues/{retire['id']}/deactivate")
        selectable = await staff.get("/api/venues")

    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert [venue["id"] for venue in selectable.json()] == [keep["id"]]


@pytest.mark.story("SCRUM-59")
async def test_deactivating_twice_leaves_the_venue_deactivated(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    # The caller asked for a state, and the venue is already in it, so this is not an error.
    async with make_client(make_user("venue_staff")) as staff:
        created = await create_venue(staff)
        first = await staff.post(f"/api/venues/{created['id']}/deactivate")
        second = await staff.post(f"/api/venues/{created['id']}/deactivate")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["is_active"] is False


@pytest.mark.story("SCRUM-59")
async def test_an_invalid_update_changes_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC5: "does not save the change" - the stored row must be untouched afterwards.
    async with make_client(make_user("venue_staff")) as client:
        created = await create_venue(client)
        response = await client.patch(
            f"/api/venues/{created['id']}", json={"maximum_capacity": 0, "location": "Moved"}
        )

    assert response.status_code == 422
    assert [problem["field"] for problem in response.json()["detail"]] == ["maximum_capacity"]

    db.expire_all()
    stored = db.get(Venue, uuid.UUID(created["id"]))
    assert stored is not None
    assert stored.maximum_capacity == 200
    assert stored.location == "Level 2, School of Computing"


@pytest.mark.story("SCRUM-59")
async def test_clearing_a_required_field_by_update_is_refused(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    # The record is validated as it would be after the change, so blanking a required
    # field is caught even though the other fields are absent from the payload.
    async with make_client(make_user("venue_staff")) as client:
        created = await create_venue(client)
        response = await client.patch(f"/api/venues/{created['id']}", json={"location": "  "})

    assert response.status_code == 422
    assert [problem["field"] for problem in response.json()["detail"]] == ["location"]


@pytest.mark.story("SCRUM-59")
async def test_updating_an_unknown_venue_is_not_found(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(f"/api/venues/{uuid.uuid4()}", json={"maximum_capacity": 10})

    assert response.status_code == 404


@pytest.mark.story("SCRUM-59")
async def test_deactivating_an_unknown_venue_is_not_found(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(f"/api/venues/{uuid.uuid4()}/deactivate")

    assert response.status_code == 404


@pytest.mark.story("SCRUM-59")
async def test_a_coordinator_cannot_update_or_deactivate_a_venue(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC2 again, for the two endpoints this change adds: a coordinator reads the
    # catalogue, and maintaining it stays with Venue Staff.
    async with make_client(make_user("venue_staff")) as staff:
        created = await create_venue(staff)

    async with make_client(make_user("coordinator")) as coordinator:
        update_attempt = await coordinator.patch(
            f"/api/venues/{created['id']}", json={"maximum_capacity": 10}
        )
        deactivate_attempt = await coordinator.post(f"/api/venues/{created['id']}/deactivate")

    assert update_attempt.status_code == 403
    assert deactivate_attempt.status_code == 403
