"""SCRUM-59: reading the venue catalogue.

Venue Staff maintain it; everyone signed in reads it (AC2). A deactivated venue leaves the
selectable list but stays readable by id (AC3, AC4), which is what soft deactivation buys
(ADR-0012). Venues are arranged directly here because the endpoints that create them land
with the story that adds them.
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
