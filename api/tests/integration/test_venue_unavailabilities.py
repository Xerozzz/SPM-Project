"""SCRUM-62 API evidence for independently achievable closure management."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from models.user import User
from models.venue import Venue
from models.venue_unavailability import VenueUnavailability

MakeUser = Callable[..., User]
MakeClient = Callable[[User | None], httpx.AsyncClient]

# Relative to now, not a fixed date: closures that have already ended are rejected, so a
# hard-coded day stops being valid once it passes.
_DAY = (datetime.now(UTC) + timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)


def at(day_offset: int, hour: int) -> str:
    """`hour`:00 UTC on `_DAY` + `day_offset`, formatted as the API returns it."""
    return (_DAY + timedelta(days=day_offset, hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        "starts_at": at(0, 9),
        "ends_at": at(0, 11),
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
    assert created.json()["starts_at"] == at(0, 9)
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
            json=body(ends_at=at(0, 12), reason="Extended maintenance"),
        )

    assert updated.status_code == 200
    assert updated.json()["reason"] == "Extended maintenance"
    assert updated.json()["ends_at"] == at(0, 12)
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
                starts_at=at(1, 9),
                ends_at=at(1, 11),
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
            json=body(ends_at=at(0, 9)),
        )

    assert inactive_response.status_code == 409
    assert invalid_response.status_code == 422
    assert invalid_response.json()["detail"] == [
        {"field": "ends_at", "reason": "must be after the start time"}
    ]


@pytest.mark.story("SCRUM-62")
async def test_create_rejects_a_closure_that_has_already_ended(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    ended_at = datetime.now(UTC) - timedelta(minutes=1)
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(
            f"/api/venues/{venue.id}/unavailabilities",
            json=body(
                starts_at=(ended_at - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                ends_at=ended_at.isoformat().replace("+00:00", "Z"),
            ),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == [{"field": "ends_at", "reason": "must be in the future"}]


@pytest.mark.story("SCRUM-62")
async def test_create_rejects_aware_non_utc_datetimes(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(
            f"/api/venues/{venue.id}/unavailabilities",
            json=body(
                starts_at="2026-10-01T17:00:00+08:00",
                ends_at="2026-10-01T19:00:00+08:00",
            ),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "starts_at", "reason": "must be given in UTC"},
        {"field": "ends_at", "reason": "must be given in UTC"},
    ]


@pytest.mark.story("SCRUM-62")
async def test_update_cannot_reach_a_closure_at_another_venue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    first_venue = make_venue(db)
    second_venue = make_venue(db)
    first_url = f"/api/venues/{first_venue.id}/unavailabilities"
    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(first_url, json=body())
        response = await client.put(
            f"/api/venues/{second_venue.id}/unavailabilities/{created.json()['id']}",
            json=body(reason="Attempted cross-venue update"),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue unavailability not found"
    assert db.get(VenueUnavailability, uuid.UUID(created.json()["id"])) is not None


@pytest.mark.story("SCRUM-62")
async def test_delete_cannot_reach_a_closure_at_another_venue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    first_venue = make_venue(db)
    second_venue = make_venue(db)
    first_url = f"/api/venues/{first_venue.id}/unavailabilities"
    async with make_client(make_user("venue_staff")) as client:
        created = await client.post(first_url, json=body())
        response = await client.delete(
            f"/api/venues/{second_venue.id}/unavailabilities/{created.json()['id']}"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue unavailability not found"
    assert db.get(VenueUnavailability, uuid.UUID(created.json()["id"])) is not None


@pytest.mark.story("SCRUM-62")
async def test_unknown_venue_is_not_available_for_listing_or_creation(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    url = f"/api/venues/{uuid.uuid4()}/unavailabilities"
    async with make_client(make_user("venue_staff")) as client:
        listed = await client.get(url)
        created = await client.post(url, json=body())

    assert listed.status_code == 404
    assert created.status_code == 404
    assert listed.json()["detail"] == "Venue not found"
    assert created.json()["detail"] == "Venue not found"


@pytest.mark.story("SCRUM-62")
async def test_update_rejects_an_unknown_closure(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        response = await client.put(
            f"/api/venues/{venue.id}/unavailabilities/{uuid.uuid4()}", json=body()
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue unavailability not found"


@pytest.mark.story("SCRUM-62")
async def test_delete_rejects_an_unknown_closure(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    async with make_client(make_user("venue_staff")) as client:
        response = await client.delete(f"/api/venues/{venue.id}/unavailabilities/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue unavailability not found"
