"""SCRUM-62 API evidence for independently achievable closure management."""

import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from models.user import User
from models.venue import Venue
from models.venue_unavailability import VenueUnavailability

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]


def make_venue(db: Session, *, is_active: bool = True) -> Venue:
    venue = Venue(
        name=f"Hall {uuid.uuid4()}",
        location="SCIS",
        maximum_capacity=100,
        facilities=[],
        supported_layouts=["theatre"],
        accessibility_features=[],
        opens_at="08:00:00",
        closes_at="22:00:00",
        is_active=is_active,
    )
    db.add(venue)
    db.flush()
    return venue


def body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "starts_at": "2026-10-01T09:00:00Z",
        "ends_at": "2026-10-01T11:00:00Z",
        "reason": "Air-conditioning maintenance",
    }
    values.update(overrides)
    return values


@pytest.mark.story("SCRUM-62")
async def test_venue_staff_create_and_list_an_unavailability(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        listed = await client.get(f"/api/venues/{venue.id}/unavailabilities")

    assert created.status_code == 201
    assert created.json()["reason"] == "Air-conditioning maintenance"
    assert created.json()["starts_at"] == "2026-10-01T09:00:00Z"
    assert [record["id"] for record in listed.json()] == [created.json()["id"]]
    assert db.get(VenueUnavailability, uuid.UUID(created.json()["id"])) is not None


@pytest.mark.story("SCRUM-62")
async def test_venue_staff_edit_a_record_without_creating_another(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        updated = await client.put(
            f"/api/venues/{venue.id}/unavailabilities/{created.json()['id']}",
            json=body(ends_at="2026-10-01T12:00:00Z", reason="Extended maintenance"),
        )

    assert updated.status_code == 200
    assert updated.json()["reason"] == "Extended maintenance"
    assert updated.json()["ends_at"] == "2026-10-01T12:00:00Z"
    assert len(db.query(VenueUnavailability).all()) == 1


@pytest.mark.story("SCRUM-62")
async def test_venue_staff_delete_a_record(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    url = f"/api/venues/{venue.id}/unavailabilities"

    async with make_client(make_user("venue_staff")) as client:
        first = await client.post(url, json=body())
        second = await client.post(
            url,
            json=body(
                starts_at="2026-10-02T09:00:00Z",
                ends_at="2026-10-02T11:00:00Z",
            ),
        )
        deleted = await client.delete(f"{url}/{first.json()['id']}")
        listed = await client.get(url)

    assert first.status_code == 201
    assert second.status_code == 201
    assert deleted.status_code == 204
    assert listed.status_code == 200
    assert [record["id"] for record in listed.json()] == [second.json()["id"]]


@pytest.mark.story("SCRUM-62")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "attendee"])
async def test_non_venue_staff_cannot_mutate_unavailability(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as staff:
        created = await staff.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
    url = f"/api/venues/{venue.id}/unavailabilities/{created.json()['id']}"

    async with make_client(make_user(role)) as client:
        create_attempt = await client.post(f"/api/venues/{venue.id}/unavailabilities", json=body())
        assert (await client.put(url, json=body(reason="Changed"))).status_code == 403
        assert (await client.delete(url)).status_code == 403
    assert create_attempt.status_code == 403


@pytest.mark.story("SCRUM-62")
async def test_create_rejects_an_inactive_venue_and_invalid_period(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    inactive = make_venue(db, is_active=False)
    active = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        inactive_response = await client.post(
            f"/api/venues/{inactive.id}/unavailabilities", json=body()
        )
        invalid_response = await client.post(
            f"/api/venues/{active.id}/unavailabilities",
            json=body(ends_at="2026-10-01T09:00:00Z"),
        )

    assert inactive_response.status_code == 409
    assert invalid_response.status_code == 422
    assert invalid_response.json()["detail"] == [
        {"field": "ends_at", "reason": "must be after the start time"}
    ]
