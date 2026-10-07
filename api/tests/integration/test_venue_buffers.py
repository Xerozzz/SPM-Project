"""SCRUM-82 AC1 and AC2: setting and reading a venue's setup and turnaround buffers.

This file covers storing and guarding the two values. Applying them to availability,
search, conflict detection and approval is the next story increment, so nothing here
asserts anything about effective occupied intervals.
"""

from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from models.venue import Venue
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_catalogue import venue_body
from tests.integration.test_venue_search import make_venue

# A venue that needs half an hour to set up and three quarters of an hour to reset: the
# worked example on the ticket (AC3).
_SETUP, _TURNAROUND = 30, 45


def problems(response: httpx.Response) -> list[dict[str, Any]]:
    detail: list[dict[str, Any]] = response.json()["detail"]
    return detail


def named_fields(response: httpx.Response) -> list[str]:
    """The fields a 422 blames, whether it came from the domain or from Pydantic.

    A domain refusal carries `field`; a Pydantic one carries `loc` ending in the field
    name. AC1 asks for the field to be identified, not for one particular shape.
    """
    return [
        problem["field"] if "field" in problem else str(problem["loc"][-1])
        for problem in problems(response)
    ]


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-82")
async def test_venue_staff_can_set_both_buffers_when_adding_a_venue(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post(
            "/api/venues",
            json=venue_body(setup_minutes=_SETUP, turnaround_minutes=_TURNAROUND),
        )

    assert response.status_code == 201, response.text
    assert response.json()["setup_minutes"] == _SETUP
    assert response.json()["turnaround_minutes"] == _TURNAROUND


@pytest.mark.story("SCRUM-82")
async def test_venue_staff_can_change_the_buffers_on_an_existing_venue(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"setup_minutes": 15, "turnaround_minutes": 20}
        )

    assert response.status_code == 200, response.text
    assert response.json()["setup_minutes"] == 15
    assert response.json()["turnaround_minutes"] == 20


@pytest.mark.story("SCRUM-82")
@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
async def test_a_negative_buffer_is_refused_and_the_field_is_named(
    db: Session, make_user: MakeUser, make_client: MakeClient, field: str
) -> None:
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post("/api/venues", json=venue_body(**{field: -1}))

    assert response.status_code == 422
    assert named_fields(response) == [field]
    # AC5's rule from SCRUM-59 still holds: an invalid record stores nothing.
    assert db.query(Venue).count() == 0


@pytest.mark.story("SCRUM-82")
@pytest.mark.parametrize("value", ["abc", 30.5])
async def test_a_buffer_that_is_not_a_whole_number_is_refused(
    make_user: MakeUser, make_client: MakeClient, value: object
) -> None:
    # AC1: text and fractional minutes are both refused, with the field named. This half
    # of AC1 is the `int` on VenueCreate rather than a domain rule, so the 422 is
    # Pydantic's; `named_fields` reads either shape.
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post("/api/venues", json=venue_body(setup_minutes=value))

    assert response.status_code == 422
    assert "setup_minutes" in named_fields(response)


@pytest.mark.story("SCRUM-82")
async def test_an_explicit_null_buffer_means_no_buffer(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    # Sending null is the same as leaving the field out: no buffer, stored as zero. The
    # column is NOT NULL, so this pins that the service substitutes the zero rather than
    # letting a null reach the database.
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post("/api/venues", json=venue_body(setup_minutes=None))

    assert response.status_code == 201, response.text
    assert response.json()["setup_minutes"] == 0


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-82")
async def test_a_coordinator_can_read_the_buffers(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db, setup_minutes=_SETUP, turnaround_minutes=_TURNAROUND)

    async with make_client(make_user("coordinator")) as client:
        response = await client.get(f"/api/venues/{venue.id}")

    assert response.status_code == 200, response.text
    assert response.json()["setup_minutes"] == _SETUP
    assert response.json()["turnaround_minutes"] == _TURNAROUND


@pytest.mark.story("SCRUM-82")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "attendee"])
async def test_only_venue_staff_may_change_the_buffers(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    venue = make_venue(db, setup_minutes=_SETUP, turnaround_minutes=_TURNAROUND)

    async with make_client(make_user(role)) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"setup_minutes": 0})

    assert response.status_code == 403
    db.refresh(venue)
    assert venue.setup_minutes == _SETUP


# --------------------------------------------------------------------------- AC7


@pytest.mark.story("SCRUM-82")
async def test_a_venue_created_without_buffers_has_none(
    make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC7: the payload that worked before this story still works, and the venue it makes
    # has no buffer, so it behaves exactly as it did.
    async with make_client(make_user("venue_staff")) as client:
        response = await client.post("/api/venues", json=venue_body())

    assert response.status_code == 201, response.text
    assert response.json()["setup_minutes"] == 0
    assert response.json()["turnaround_minutes"] == 0
