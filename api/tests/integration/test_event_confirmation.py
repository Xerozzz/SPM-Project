"""SCRUM-80 API evidence: the assigned Coordinator confirms an event.

Against real PostgreSQL, because the two things that matter most here are not pure: the
conversion of holds and the status move have to land in one transaction (AC4, AC5), and
the prerequisites have to be rechecked against committed state rather than whatever a
screen last saw (AC7, AC11).

Every test starts from `ready_event` — SCRUM-79's arranged plan plus a safety approval of
exactly that plan, which is the only state AC2 lets a confirmation happen from — and then
breaks one thing.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from domain.equipment_requirement import RequirementFields
from domain.event_status import EventStatus
from domain.roles import Role
from domain.safety_review import SafetyDecision, fingerprint
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from services import equipment_requirements as requirement_service
from services import safety_reviews as safety_service
from tests.integration.test_equipment_requirements import catalogue
from tests.integration.test_safety_review import _NOW, _START, arranged_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_search import effective_for, make_venue


def approve_safety(db: Session, event: EventRequest, make_user: MakeUser) -> None:
    """Record a Safety Officer approval of the event's plan exactly as it stands."""
    plan = safety_service.plan_of(db, event, _NOW)
    safety_service.record(
        db,
        event,
        SafetyDecision.APPROVE,
        "Egress and capacity check out.",
        fingerprint(plan),
        make_user(Role.SAFETY_OFFICER.value).id,
        _NOW,
    )


def ready_event(db: Session, make_user: MakeUser) -> tuple[EventRequest, VenueBooking, User]:
    """An arranged event whose plan a Safety Officer has approved."""
    event, booking, coordinator = arranged_event(db, make_user)
    approve_safety(db, event, make_user)
    db.flush()
    return event, booking, coordinator


def stored_event(db: Session, event_id: uuid.UUID) -> EventRequest:
    """The event as the database now holds it, not as the test's object remembers it."""
    row = db.get(EventRequest, event_id)
    assert row is not None
    return row


def stored_booking(db: Session, booking_id: uuid.UUID) -> VenueBooking:
    row = db.get(VenueBooking, booking_id)
    assert row is not None
    return row


def reasons_of(payload: dict[str, object]) -> list[str]:
    detail = payload["detail"]
    assert isinstance(detail, dict)
    arrangement = detail.get("arrangement_blockers") or []
    safety = detail.get("safety_blockers") or []
    assert isinstance(arrangement, list) and isinstance(safety, list)
    return [str(row) for row in arrangement] + [str(row) for row in safety]


@pytest.mark.story("SCRUM-80")
async def test_an_arranged_and_approved_event_is_confirmed_with_its_holds(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: the event becomes Confirmed and its live holds become real bookings."""
    event, booking, coordinator = ready_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert [row["session_label"] for row in body["confirmed_bookings"]] == [booking.session_label]

    db.expire_all()
    assert stored_event(db, event.id).status is EventStatus.CONFIRMED
    assert stored_booking(db, booking.id).status is BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-80")
async def test_confirmation_records_who_did_it_and_when(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6: the actor and time are recorded, separately from the SCRUM-31 decision."""
    event, _, coordinator = ready_event(db, make_user)

    async with make_client(coordinator) as client:
        body = (await client.post(f"/api/event-requests/{event.id}/confirm")).json()

    assert body["confirmed_by_id"] == str(coordinator.id)
    assert body["confirmed_at"] is not None
    db.expire_all()
    stored = stored_event(db, event.id)
    assert stored.confirmed_by_id == coordinator.id
    assert stored.confirmed_at is not None


@pytest.mark.story("SCRUM-80")
async def test_only_the_assigned_coordinator_may_confirm(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1. Another coordinator, the organiser and the Safety Officer are all refused."""
    event, _, _ = ready_event(db, make_user)

    for other in ("coordinator", "organiser", Role.SAFETY_OFFICER.value, "coordinator_lead"):
        async with make_client(make_user(other)) as client:
            response = await client.post(f"/api/event-requests/{event.id}/confirm")
        assert response.status_code == 403, f"{other} could confirm"

    db.expire_all()
    assert stored_event(db, event.id).status is EventStatus.APPROVED


@pytest.mark.story("SCRUM-80")
async def test_an_event_with_no_safety_review_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: the customer makes safety approval a precondition for confirmation."""
    event, _, coordinator = arranged_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 409
    assert reasons_of(response.json()) == ["safety_not_reviewed"]


@pytest.mark.story("SCRUM-80")
async def test_an_event_the_officer_sent_back_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: a rejection is not an approval, however recent."""
    event, _, coordinator = arranged_event(db, make_user)
    plan = safety_service.plan_of(db, event, _NOW)
    safety_service.record(
        db,
        event,
        SafetyDecision.REJECT,
        "Only one exit.",
        fingerprint(plan),
        make_user(Role.SAFETY_OFFICER.value).id,
        _NOW,
    )

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 409
    assert reasons_of(response.json()) == ["safety_not_approved"]


@pytest.mark.story("SCRUM-80")
async def test_an_approval_of_a_plan_that_has_since_changed_cannot_confirm(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC7, and the reason ADR-0048 stores a fingerprint at all.

    The Officer approved the plan. A requirement was added afterwards, so nobody has
    judged the event as it now stands and the earlier approval is spent.
    """
    event, _, coordinator = ready_event(db, make_user)
    catalogue(db, "Microphone")
    requirement_service.add(
        db,
        event,
        RequirementFields(equipment_type="Microphone", quantity=1),
        coordinator.id,
        _NOW,
    )
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 409
    # The new requirement is unreviewed, so that blocks too; the point is that the
    # stale approval is reported rather than silently carrying the confirmation.
    assert "safety_approval_stale" in reasons_of(response.json())
    db.expire_all()
    assert stored_event(db, event.id).status is EventStatus.APPROVED


@pytest.mark.story("SCRUM-80")
async def test_a_refused_confirmation_changes_nothing_at_all(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: no partial confirmation. The hold stays a hold and the event stays planned."""
    event, booking, coordinator = arranged_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 409
    db.expire_all()
    assert stored_event(db, event.id).status is EventStatus.APPROVED
    assert stored_booking(db, booking.id).status is BookingStatus.TENTATIVE
    assert stored_event(db, event.id).confirmed_at is None


@pytest.mark.story("SCRUM-80")
async def test_an_expired_hold_blocks_confirmation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC3 and AC8: a hold that has run out is not an arrangement to commit.

    The expiry is set behind the sweep (ADR-0030 changes the status on a timer), so this
    is the case where the row still reads Tentative and only the clock says otherwise.
    """
    event, booking, coordinator = ready_event(db, make_user)
    booking.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 409
    assert "hold_expired" in reasons_of(response.json())
    db.expire_all()
    assert stored_booking(db, booking.id).status is BookingStatus.TENTATIVE


@pytest.mark.story("SCRUM-80")
async def test_a_superseded_booking_does_not_block_confirmation(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC10: a rejected request is history, not a current requirement.

    Nobody can clear a rejection, so judging one would make the event unconfirmable for
    good — the same trap SCRUM-79 found in its own plan rule.
    """
    event, booking, coordinator = ready_event(db, make_user)
    venue = make_venue(db, name=f"Hall {uuid.uuid4()}")
    effective_start, effective_end = effective_for(venue, _START, _START + timedelta(hours=2))
    db.add(
        VenueBooking(
            venue_id=venue.id,
            event_request_id=event.id,
            requested_by_id=coordinator.id,
            session_label="Tried and refused",
            start_at=_START,
            end_at=_START + timedelta(hours=2),
            effective_start_at=effective_start,
            effective_end_at=effective_end,
            status=BookingStatus.REJECTED,
        )
    )
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 200
    db.expire_all()
    assert stored_booking(db, booking.id).status is BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-80")
async def test_an_event_cannot_be_confirmed_twice(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2 through the status: a confirmed event is not in planning any more."""
    event, _, coordinator = ready_event(db, make_user)

    async with make_client(coordinator) as client:
        first = await client.post(f"/api/event-requests/{event.id}/confirm")
        second = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert first.status_code == 200
    assert second.status_code == 409
    assert reasons_of(second.json()) == ["not_in_planning"]


@pytest.mark.story("SCRUM-80")
async def test_the_screen_can_ask_what_is_still_missing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2, AC3 and AC10: readiness reports rather than refuses, in two lists.

    Kept apart because they are owed by different people: the Coordinator can chase an
    arrangement, but only the Officer can clear a safety reason.
    """
    event, _, coordinator = arranged_event(db, make_user)

    async with make_client(coordinator) as client:
        before = (await client.get(f"/api/event-requests/{event.id}/confirmation")).json()

    assert before["may_confirm"] is False
    assert before["arrangement_blockers"] == []
    assert before["safety_blockers"] == ["safety_not_reviewed"]

    approve_safety(db, event, make_user)
    db.flush()

    async with make_client(coordinator) as client:
        after = (await client.get(f"/api/event-requests/{event.id}/confirmation")).json()

    assert after["may_confirm"] is True
    assert after["arrangement_blockers"] == [] and after["safety_blockers"] == []


@pytest.mark.story("SCRUM-80")
async def test_readiness_is_the_assigned_coordinators_question(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 covers the read as well: it says what an event is still waiting on."""
    event, _, _ = ready_event(db, make_user)

    async with make_client(make_user("coordinator")) as client:
        response = await client.get(f"/api/event-requests/{event.id}/confirmation")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-80")
async def test_an_approval_after_a_rejection_clears_the_way(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2 names the *latest* applicable review, and the order genuinely matters.

    An Officer who rejects and is then satisfied has granted an approval. Reading the
    wrong end of the history would leave this event permanently unconfirmable.
    """
    event, _, coordinator = arranged_event(db, make_user)
    officer_id = make_user(Role.SAFETY_OFFICER.value).id
    plan = safety_service.plan_of(db, event, _NOW)
    safety_service.record(
        db, event, SafetyDecision.REJECT, "Only one exit.", fingerprint(plan), officer_id, _NOW
    )
    safety_service.record(
        db,
        event,
        SafetyDecision.APPROVE,
        "Second exit confirmed.",
        fingerprint(plan),
        officer_id,
        _NOW + timedelta(hours=1),
    )
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 200
    db.expire_all()
    assert stored_event(db, event.id).status is EventStatus.CONFIRMED


@pytest.mark.story("SCRUM-80")
async def test_a_rejection_after_an_approval_withdraws_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The other direction: an Officer who looks again has withdrawn the approval.

    Reading the history oldest-first passes the test above and fails this one, which is
    why both directions are here.
    """
    event, _, coordinator = arranged_event(db, make_user)
    officer_id = make_user(Role.SAFETY_OFFICER.value).id
    plan = safety_service.plan_of(db, event, _NOW)
    safety_service.record(
        db, event, SafetyDecision.APPROVE, "Looked fine.", fingerprint(plan), officer_id, _NOW
    )
    safety_service.record(
        db,
        event,
        SafetyDecision.REJECT,
        "Looked again; the exit is blocked.",
        fingerprint(plan),
        officer_id,
        _NOW + timedelta(hours=1),
    )
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 409
    assert reasons_of(response.json()) == ["safety_not_approved"]
    db.expire_all()
    assert stored_event(db, event.id).status is EventStatus.APPROVED
