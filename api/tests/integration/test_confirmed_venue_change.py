"""SCRUM-118: cancel one arrangement of a Confirmed event as a venue change.

`POST /api/event-requests/{id}/venue-bookings/{booking_id}/venue-change`. The Confirmed
event is made the way SCRUM-80 confirms one (arranged, safety approved, confirmed), and
the refusals reuse SCRUM-109's fixtures, so this proves the same rules, not copies of them.
Every refusal also proves nothing changed: arrangement, status, safety approval, intake.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_replanning import ReplanCause
from domain.event_status import EventStatus
from domain.notifications import NotificationType
from domain.venue_booking import BookingStatus
from models.event_registration import EventRegistration
from models.event_request import EventRequest
from models.notification import Notification
from models.safety_review import SafetyReview
from models.user import User
from models.venue_booking import VenueBooking
from repositories import safety_reviews as safety_repo
from services import event_confirmations, lifecycle_notifications, venue_changes
from services import registration_intake as intake_service
from tests.integration.test_cancel_venue_arrangement import Planning, arrangement, snapshot, venue
from tests.integration.test_intake_suspension_on_replan import _register
from tests.integration.test_safety_approval_invalidation import _confirmed
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeClient, MakeUser

REASON = "Hall flooded"


@dataclass
class Confirmed:
    event: EventRequest
    booking: VenueBooking
    coordinator: User
    other: VenueBooking
    attendee: User


def confirmed(db: Session, make_user: MakeUser) -> Confirmed:
    """A Confirmed event with open intake, one registration and a second arrangement.

    Committed, as SCRUM-132's rollback test does: a refused or failed venue change rolls
    its own transaction back, and that must not take the setup with it."""
    event, booking, coordinator = _confirmed(db, make_user)
    event.registration_opened_at = _NOW
    event.registration_closes_at = _NOW + timedelta(days=1)
    db.flush()
    attendee = make_user("attendee")
    _register(db, event, attendee, _NOW)
    plan = Planning(event, coordinator, make_user("venue_staff"))
    other = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    db.commit()
    return Confirmed(event, booking, coordinator, other, attendee)


async def venue_change(
    client: httpx.AsyncClient, event: EventRequest, booking: VenueBooking, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/event-requests/{event.id}/venue-bookings/{booking.id}/venue-change", json=body
    )


CONFIRMED_BODY = {"reason": REASON, "confirm_venue_change": True}


def approval(db: Session, event: EventRequest) -> SafetyReview:
    return safety_repo.list_for_event(db, event.id)[-1]


def registrations(db: Session, event: EventRequest) -> list[tuple[object, object]]:
    rows = db.scalars(
        select(EventRegistration).where(EventRegistration.event_request_id == event.id)
    )
    return sorted((r.id, r.status) for r in rows)


def state(db: Session, c: Confirmed) -> tuple[object, ...]:
    """Everything AC3 says must not change, as the database now holds it."""
    db.expire_all()
    event = db.get(EventRequest, c.event.id)
    assert event is not None
    latest = approval(db, c.event)
    return (
        snapshot(db, c.booking),
        snapshot(db, c.other),
        event.status,
        event.registration_suspended_at,
        latest.invalidated_at,
        latest.invalidation_cause,
        registrations(db, c.event),
    )


# ------------------------------------------------------------------- AC2, AC5


@pytest.mark.story("SCRUM-118")
async def test_a_venue_change_cancels_the_arrangement_and_returns_the_event_to_planning(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    c = confirmed(db, make_user)
    other_before = snapshot(db, c.other)
    kept = registrations(db, c.event)

    async with make_client(c.coordinator) as client:
        response = await venue_change(client, c.event, c.booking, CONFIRMED_BODY)

    assert response.status_code == 200
    body = response.json()
    assert (body["event_status"], body["booking"]["status"]) == ("approved", "cancelled")
    db.expire_all()
    booking = db.get(VenueBooking, c.booking.id)
    assert booking is not None
    assert booking.status is BookingStatus.CANCELLED
    assert (booking.cancelled_by_id, booking.cancellation_reason) == (c.coordinator.id, REASON)
    event = db.get(EventRequest, c.event.id)
    assert event is not None
    assert event.status is EventStatus.APPROVED
    assert event.registration_suspended_at is not None
    latest = approval(db, c.event)
    assert latest.invalidated_at is not None
    assert latest.invalidation_cause == ReplanCause.VENUE_CANCELLATION.value
    # AC2: existing registrations are kept. AC5: the other arrangement is untouched.
    assert registrations(db, c.event) == kept
    assert snapshot(db, c.other) == other_before


@pytest.mark.story("SCRUM-118")
async def test_the_shared_replanning_stages_the_event_replanned_notice(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0066: accepted on purpose, as for a venue closure; delivery is SCRUM-50's."""
    c = confirmed(db, make_user)

    async with make_client(c.coordinator) as client:
        assert (await venue_change(client, c.event, c.booking, CONFIRMED_BODY)).status_code == 200

    sent = db.scalars(
        select(Notification).where(
            Notification.event_request_id == c.event.id,
            Notification.type == NotificationType.EVENT_REPLANNED,
            Notification.recipient_id == c.attendee.id,
        )
    )
    assert len(list(sent)) == 1


# ------------------------------------------------------------------------ AC1


@pytest.mark.story("SCRUM-118")
@pytest.mark.parametrize(
    ("body", "fields"),
    [
        ({"reason": REASON}, ["confirm_venue_change"]),
        ({"reason": REASON, "confirm_venue_change": False}, ["confirm_venue_change"]),
        ({"reason": "   ", "confirm_venue_change": True}, ["reason"]),
        ({}, ["confirm_venue_change", "reason"]),
    ],
)
async def test_without_confirmation_or_a_reason_nothing_changes(
    body: dict[str, Any],
    fields: list[str],
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    c = confirmed(db, make_user)
    before = state(db, c)

    async with make_client(c.coordinator) as client:
        response = await venue_change(client, c.event, c.booking, body)

    assert response.status_code == 422
    assert [problem["field"] for problem in response.json()["detail"]] == fields
    assert state(db, c) == before


# ------------------------------------------------------------------------ AC3


@pytest.mark.story("SCRUM-118")
@pytest.mark.parametrize(
    ("module", "name"),
    [(intake_service, "suspend"), (lifecycle_notifications, "replanned")],
)
def test_a_failure_in_any_part_changes_nothing(
    module: object,
    name: str,
    db: Session,
    make_user: MakeUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cancellation is staged before the replanning fails; it must not survive it."""
    c = confirmed(db, make_user)
    before = state(db, c)

    def broken(*_: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(module, name, broken)
    with pytest.raises(RuntimeError):
        venue_changes.cancel_for_venue_change(
            db, c.event.id, c.booking.id, c.coordinator.id, REASON, True, datetime.now(UTC)
        )
    monkeypatch.undo()

    assert state(db, c) == before


# ------------------------------------------------------------------------ AC4


@pytest.mark.story("SCRUM-118")
async def test_the_event_is_not_confirmed_again_without_a_new_safety_approval(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    c = confirmed(db, make_user)
    async with make_client(c.coordinator) as client:
        assert (await venue_change(client, c.event, c.booking, CONFIRMED_BODY)).status_code == 200
    db.expire_all()
    event = db.get(EventRequest, c.event.id)
    assert event is not None

    with pytest.raises(event_confirmations.NotConfirmableError) as refused:
        event_confirmations.confirm(db, event, c.coordinator.id, datetime.now(UTC))

    assert refused.value.problems.safety
    db.expire_all()
    stored = db.get(EventRequest, c.event.id)
    assert stored is not None
    assert stored.status is EventStatus.APPROVED


# ------------------------------------------------------------------------ AC6


@pytest.mark.story("SCRUM-118")
@pytest.mark.parametrize("caller", ["unassigned_coordinator", "owner", "coordinator_lead"])
async def test_anyone_but_the_assigned_coordinator_is_refused_and_nothing_changes(
    caller: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    c = confirmed(db, make_user)
    before = state(db, c)
    owner = db.get(User, c.event.organiser_id)
    viewer = owner if caller == "owner" else make_user(caller.replace("unassigned_", ""))
    assert viewer is not None

    async with make_client(viewer) as client:
        response = await venue_change(client, c.event, c.booking, CONFIRMED_BODY)

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert state(db, c) == before


@pytest.mark.story("SCRUM-118")
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (BookingStatus.CANCELLED, "This arrangement has already been cancelled"),
        (BookingStatus.REJECTED, "This arrangement was rejected and cannot be cancelled"),
        (BookingStatus.EXPIRED, "This hold has expired and cannot be cancelled"),
    ],
)
async def test_an_arrangement_no_longer_live_is_refused_as_in_scrum_109(
    status: BookingStatus,
    message: str,
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    """The event stays Confirmed: a refused cancellation starts no venue change."""
    c = confirmed(db, make_user)
    plan = Planning(c.event, c.coordinator, make_user("venue_staff"))
    dead = arrangement(db, plan, venue(db), status)
    db.commit()
    before = state(db, c)

    async with make_client(c.coordinator) as client:
        response = await venue_change(client, c.event, dead, CONFIRMED_BODY)

    assert response.status_code == 409
    assert response.json() == {"detail": message}
    assert state(db, c) == before


@pytest.mark.story("SCRUM-118")
async def test_an_event_in_planning_is_sent_to_the_ordinary_cancellation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    c = confirmed(db, make_user)
    c.event.status = EventStatus.APPROVED
    db.commit()
    before = snapshot(db, c.other)

    async with make_client(c.coordinator) as client:
        response = await venue_change(client, c.event, c.other, CONFIRMED_BODY)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Only a confirmed event's arrangements are cancelled as a venue change"
    }
    assert snapshot(db, c.other) == before


# --------------------------------------------------------------- arrangements list


@pytest.mark.story("SCRUM-118")
async def test_the_assigned_coordinator_lists_a_confirmed_events_arrangements(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    c = confirmed(db, make_user)

    async with make_client(c.coordinator) as client:
        response = await client.get(f"/api/event-requests/{c.event.id}/venue-arrangements")

    assert response.status_code == 200
    listed = {(row["id"], row["status"]) for row in response.json()}
    assert listed == {(str(c.booking.id), "confirmed"), (str(c.other.id), "pending")}


@pytest.mark.story("SCRUM-118")
@pytest.mark.parametrize("caller", ["unassigned_coordinator", "owner", "venue_staff"])
async def test_no_one_else_lists_the_arrangements(
    caller: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    c = confirmed(db, make_user)
    owner = db.get(User, c.event.organiser_id)
    viewer = owner if caller == "owner" else make_user(caller.replace("unassigned_", ""))
    assert viewer is not None

    async with make_client(viewer) as client:
        response = await client.get(f"/api/event-requests/{c.event.id}/venue-arrangements")

    assert response.status_code == 403
