"""SCRUM-109: the assigned Coordinator cancels one venue arrangement, through the route.

`POST /api/event-requests/{id}/venue-bookings/{booking_id}/cancel`. Each refusal also
proves nothing changed. The races (AC10) and the no-commit reuse are in
test_cancel_venue_arrangement_races.py, because they need committed rows.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from services import venue_bookings
from tests.integration.cancelled_rows import cancellation_record
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for, make_venue, search_params

_START = datetime(2031, 3, 4, 2, 0, tzinfo=UTC)  # 10:00 in Singapore
_END = _START + timedelta(hours=2)
_REASON = "Venue no longer needed"


@dataclass
class Planning:
    event: EventRequest
    coordinator: User
    staff: User


def planning(db: Session, make_user: MakeUser) -> Planning:
    """An Approved event assigned to its own Coordinator, and a Venue Staff member."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, start_at=_START, end_at=_END)
    return Planning(event, coordinator, make_user("venue_staff"))


def venue(db: Session, **buffers: int) -> Venue:
    tag = uuid.uuid4().hex[:8]
    return make_venue(db, name=f"Cancel hall {tag}", location=f"Cancel test {tag}", **buffers)


def arrangement(
    db: Session,
    plan: Planning,
    where: Venue,
    status: BookingStatus,
    start_at: datetime = _START,
    end_at: datetime = _END,
    expires_at: datetime | None = None,
) -> VenueBooking:
    """One of the event's arrangements in `status`, with the history that status implies."""
    now = datetime.now(UTC)
    effective_start, effective_end = effective_for(where, start_at, end_at)
    held = status in (BookingStatus.TENTATIVE, BookingStatus.EXPIRED)
    if held and expires_at is None:
        expires_at = now + timedelta(days=2) if status is BookingStatus.TENTATIVE else now
    decided = status in (BookingStatus.REJECTED, BookingStatus.CONFIRMED)
    row = VenueBooking(
        venue_id=where.id,
        event_request_id=plan.event.id,
        requested_by_id=plan.coordinator.id,
        session_label="Opening keynote",
        start_at=start_at,
        end_at=end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=status,
        expires_at=expires_at,
        held_by_id=plan.staff.id if held else None,
        held_at=now if held else None,
        decided_by_id=plan.staff.id if decided else None,
        decided_at=now if decided else None,
        decision_reason="Fits the session" if decided else None,
        **cancellation_record(status, plan.coordinator.id),
    )
    db.add(row)
    db.flush()
    return row


def snapshot(db: Session, row: VenueBooking) -> dict[str, object]:
    """Every column of the row as the database now has it."""
    db.expire_all()
    fresh = db.get(VenueBooking, row.id)
    assert fresh is not None
    return {column.key: getattr(fresh, column.key) for column in VenueBooking.__table__.columns}


async def cancel(
    client: httpx.AsyncClient,
    event: EventRequest,
    booking: VenueBooking,
    reason: str | None = _REASON,
) -> httpx.Response:
    body = {} if reason is None else {"reason": reason}
    return await client.post(
        f"/api/event-requests/{event.id}/venue-bookings/{booking.id}/cancel", json=body
    )


# ------------------------------------------------------------------ AC1, AC2


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    "target", [BookingStatus.PENDING, BookingStatus.TENTATIVE, BookingStatus.CONFIRMED]
)
async def test_only_the_chosen_arrangement_is_cancelled(
    target: BookingStatus, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1: an event with a request, a hold and a booking (plus a second request); only
    the chosen one becomes Cancelled."""
    plan = planning(db, make_user)
    rows = {
        status: arrangement(db, plan, venue(db), status)
        for status in (BookingStatus.PENDING, BookingStatus.TENTATIVE, BookingStatus.CONFIRMED)
    }
    sibling = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    others = [row for status, row in rows.items() if status is not target] + [sibling]
    before = {row.id: snapshot(db, row) for row in others}

    async with make_client(plan.coordinator) as client:
        response = await cancel(client, plan.event, rows[target])

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(rows[target].id)
    assert body["status"] == "cancelled"
    assert body["cancellation_reason"] == _REASON
    assert body["cancelled_by_id"] == str(plan.coordinator.id)
    assert {row.id: snapshot(db, row) for row in others} == before
    assert snapshot(db, rows[target])["status"] is BookingStatus.CANCELLED


@pytest.mark.story("SCRUM-109")
async def test_the_cancelled_record_keeps_its_history(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: venue, period, the earlier decision and hold history are kept, and who, when
    and why are added. Nothing is deleted."""
    plan = planning(db, make_user)
    booking = arrangement(
        db, plan, venue(db), BookingStatus.CONFIRMED, expires_at=_START - timedelta(days=1)
    )
    booking.held_by_id = plan.staff.id
    booking.held_at = datetime.now(UTC) - timedelta(days=3)
    db.flush()
    before = snapshot(db, booking)
    count = db.query(VenueBooking).filter_by(event_request_id=plan.event.id).count()
    sent = datetime.now(UTC)

    async with make_client(plan.coordinator) as client:
        response = await cancel(client, plan.event, booking, reason="  Hall flooded  ")

    assert response.status_code == 200
    after = snapshot(db, booking)
    changed = {key for key in after if after[key] != before[key]}
    assert changed == {"status", "cancelled_by_id", "cancelled_at", "cancellation_reason"}
    assert after["status"] is BookingStatus.CANCELLED
    assert after["cancelled_by_id"] == plan.coordinator.id
    assert after["cancellation_reason"] == "Hall flooded"
    cancelled_at = after["cancelled_at"]
    assert isinstance(cancelled_at, datetime) and cancelled_at.utcoffset() == timedelta(0)
    assert sent <= cancelled_at <= datetime.now(UTC)
    assert db.query(VenueBooking).filter_by(event_request_id=plan.event.id).count() == count


# ------------------------------------------------------------------ AC3


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize("status", [BookingStatus.TENTATIVE, BookingStatus.CONFIRMED])
async def test_a_cancelled_hold_or_booking_frees_its_slot_including_buffers(
    status: BookingStatus, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3: availability, search, the calendar and approval of another request all see
    the slot as free — for a request that clashed only through setup and turnaround."""
    hall = venue(db, setup_minutes=30, turnaround_minutes=30)
    plan = planning(db, make_user)
    blocking = arrangement(db, plan, hall, status)
    # 45 minutes after it ends: clear of the event itself, inside the 30 + 30 buffers.
    other = planning(db, make_user)
    later = arrangement(
        db,
        other,
        hall,
        BookingStatus.PENDING,
        _END + timedelta(minutes=45),
        _END + timedelta(hours=2),
    )
    period = {"start_at": later.start_at.isoformat(), "end_at": later.end_at.isoformat()}
    expiry = {"expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()}

    async def observe() -> tuple[bool, bool, bool]:
        async with make_client(plan.coordinator) as client:
            free = await client.get(
                "/api/venue-calendar/availability", params={"venue_id": str(hall.id), **period}
            )
            found = await client.get(
                "/api/venues/search", params=search_params(location=hall.location, **period)
            )
            shown = await client.get(
                "/api/venue-calendar",
                params={
                    "venue_id": str(hall.id),
                    "start_at": _START.isoformat(),
                    "end_at": later.end_at.isoformat(),
                },
            )
        blocked_on_calendar = any(entry["id"] == str(blocking.id) for entry in shown.json())
        listed = any(row["id"] == str(hall.id) for row in found.json())
        return free.json()["available"], listed, blocked_on_calendar

    assert await observe() == (False, False, True)
    async with make_client(other.staff) as client:
        refused = await client.post(f"/api/venue-bookings/{later.id}/approve", json=expiry)
    assert refused.status_code == 409

    async with make_client(plan.coordinator) as client:
        assert (await cancel(client, plan.event, blocking)).status_code == 200

    assert await observe() == (True, True, False)
    async with make_client(other.staff) as client:
        approved = await client.post(f"/api/venue-bookings/{later.id}/approve", json=expiry)
    assert approved.status_code == 200
    assert approved.json()["status"] == "tentative"


# ------------------------------------------------------------------ AC4, AC5


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    "reason", [None, "", "   ", "\t\n "], ids=["missing", "empty", "spaces", "ws"]
)
async def test_a_blank_reason_is_a_field_error_and_changes_nothing(
    reason: str | None, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    plan = planning(db, make_user)
    booking = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    before = snapshot(db, booking)

    async with make_client(plan.coordinator) as client:
        response = await cancel(client, plan.event, booking, reason=reason)

    assert response.status_code == 422
    assert response.json() == {"detail": [{"field": "reason", "reason": "is required"}]}
    assert snapshot(db, booking) == before


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    ("status", "expires_in", "message"),
    [
        (BookingStatus.CANCELLED, None, "This arrangement has already been cancelled"),
        (BookingStatus.REJECTED, None, "This arrangement was rejected and cannot be cancelled"),
        (BookingStatus.EXPIRED, None, "This hold has expired and cannot be cancelled"),
        # Due but not yet marked Expired by the minute timer (AC10).
        (
            BookingStatus.TENTATIVE,
            timedelta(seconds=-1),
            "This hold has expired and cannot be cancelled",
        ),
    ],
    ids=["cancelled", "rejected", "expired", "hold-at-expiry"],
)
async def test_an_arrangement_that_holds_nothing_cannot_be_cancelled(
    status: BookingStatus,
    expires_in: timedelta | None,
    message: str,
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    plan = planning(db, make_user)
    expires_at = None if expires_in is None else datetime.now(UTC) + expires_in
    booking = arrangement(db, plan, venue(db), status, expires_at=expires_at)
    before = snapshot(db, booking)

    async with make_client(plan.coordinator) as client:
        response = await cancel(client, plan.event, booking)

    assert response.status_code == 409
    assert response.json() == {"detail": message}
    assert snapshot(db, booking) == before


# ------------------------------------------------------------------ AC6


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    "caller_kind",
    ["unassigned_coordinator", "venue_staff", "owning_organiser", "coordinator_lead", "anonymous"],
)
async def test_anyone_but_the_assigned_coordinator_is_refused(
    caller_kind: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    owner = make_user("organiser")
    coordinator = make_user("coordinator")
    event = approved_event(db, owner, coordinator, start_at=_START, end_at=_END)
    plan = Planning(event, coordinator, make_user("venue_staff"))
    booking = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    before = snapshot(db, booking)
    callers: dict[str, User | None] = {
        "unassigned_coordinator": make_user("coordinator"),
        "venue_staff": plan.staff,
        "owning_organiser": owner,
        "coordinator_lead": make_user("coordinator_lead"),
        "anonymous": None,
    }

    async with make_client(callers[caller_kind]) as client:
        response = await cancel(client, event, booking)

    assert response.status_code == (401 if caller_kind == "anonymous" else 403)
    assert snapshot(db, booking) == before


@pytest.mark.story("SCRUM-109")
async def test_reassignment_moves_the_right_to_cancel(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6: after the Lead reassigns, the outgoing Coordinator is refused and the
    incoming one may cancel."""
    plan = planning(db, make_user)
    incoming = make_user("coordinator")
    booking = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    async with make_client(make_user("coordinator_lead")) as client:
        moved = await client.post(
            f"/api/event-requests/{plan.event.id}/reassign",
            json={
                "coordinator_id": str(incoming.id),
                "expected_current_coordinator_id": str(plan.coordinator.id),
            },
        )
    assert moved.status_code == 200
    before = snapshot(db, booking)

    async with make_client(plan.coordinator) as client:
        outgoing = await cancel(client, plan.event, booking)
    assert outgoing.status_code == 403
    assert snapshot(db, booking) == before

    async with make_client(incoming) as client:
        allowed = await cancel(client, plan.event, booking)
    assert allowed.status_code == 200
    assert allowed.json()["cancelled_by_id"] == str(incoming.id)


@pytest.mark.story("SCRUM-109")
async def test_another_events_arrangement_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Naming someone else's booking under your own event discloses nothing."""
    plan = planning(db, make_user)
    elsewhere = arrangement(db, planning(db, make_user), venue(db), BookingStatus.PENDING)
    before = snapshot(db, elsewhere)

    async with make_client(plan.coordinator) as client:
        foreign = await cancel(client, plan.event, elsewhere)
        unknown = await client.post(
            f"/api/event-requests/{plan.event.id}/venue-bookings/{uuid.uuid4()}/cancel",
            json={"reason": _REASON},
        )

    assert (foreign.status_code, unknown.status_code) == (404, 404)
    assert foreign.json() == {"detail": "Venue booking not found"}
    assert snapshot(db, elsewhere) == before


@pytest.mark.story("SCRUM-109")
def test_staging_for_an_event_that_does_not_exist_is_not_found(
    db: Session, make_user: MakeUser
) -> None:
    """The route's access check answers 404 first; SCRUM-115 and SCRUM-116 call the
    service directly, so it must refuse an unknown event on its own."""
    with pytest.raises(venue_bookings.BookingNotFoundError):
        venue_bookings.stage_cancellation(
            db, uuid.uuid4(), uuid.uuid4(), make_user("coordinator").id, _REASON, datetime.now(UTC)
        )


# ------------------------------------------------------------------ AC7, AC9


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (
            EventStatus.CONFIRMED,
            # SCRUM-118 names the venue-change action this event now goes through.
            "This event is confirmed: cancelling an arrangement starts a venue change",
        ),
        *[
            (status, "Venue arrangements can only be cancelled while the event is being planned")
            for status in EventStatus
            if status not in (EventStatus.APPROVED, EventStatus.CONFIRMED)
        ],
    ],
)
async def test_an_event_outside_planning_refuses_with_a_reason(
    status: EventStatus,
    message: str,
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    """AC7 (every status but Approved, so Cancelled or Completed will be too) and AC9."""
    plan = planning(db, make_user)
    booking = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    plan.event.status = status
    db.flush()
    before = snapshot(db, booking)

    async with make_client(plan.coordinator) as client:
        response = await cancel(client, plan.event, booking)

    assert response.status_code == 409
    assert response.json() == {"detail": message}
    assert snapshot(db, booking) == before
    db.refresh(plan.event)
    assert plan.event.status is status


# ------------------------------------------------------------------ AC8, AC11


@pytest.mark.story("SCRUM-109")
async def test_cancelling_does_not_touch_the_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC8: the event's status and last change are as they were."""
    plan = planning(db, make_user)
    booking = arrangement(db, plan, venue(db), BookingStatus.TENTATIVE)
    db.refresh(plan.event)
    before = (plan.event.status, plan.event.updated_at, plan.event.coordinator_id)

    async with make_client(plan.coordinator) as client:
        assert (await cancel(client, plan.event, booking)).status_code == 200

    db.expire_all()
    event = db.get(EventRequest, plan.event.id)
    assert event is not None
    assert (event.status, event.updated_at, event.coordinator_id) == before


@pytest.mark.story("SCRUM-109")
async def test_the_list_shows_the_cancelled_one_with_its_reason_beside_the_others(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC11: the Coordinator's arrangement list."""
    plan = planning(db, make_user)
    kept = arrangement(db, plan, venue(db), BookingStatus.PENDING)
    gone = arrangement(db, plan, venue(db), BookingStatus.TENTATIVE)

    async with make_client(plan.coordinator) as client:
        assert (await cancel(client, plan.event, gone)).status_code == 200
        listed = await client.get(f"/api/event-requests/{plan.event.id}/venue-bookings")

    assert listed.status_code == 200
    by_id = {row["id"]: row for row in listed.json()}
    assert (by_id[str(gone.id)]["status"], by_id[str(gone.id)]["cancellation_reason"]) == (
        "cancelled",
        _REASON,
    )
    assert (by_id[str(kept.id)]["status"], by_id[str(kept.id)]["cancellation_reason"]) == (
        "pending",
        None,
    )
