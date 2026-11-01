"""SCRUM-80 AC11: confirmation is safe against a concurrent hold expiry, and it does not
reopen suspended registration.

The race test follows SCRUM-109's pattern: the expiry timer takes the booking lock and
keeps its transaction open, confirmation runs in a thread, the test waits until Postgres
reports that thread waiting for the lock, and only then does the timer commit. The rows
must be committed for the second connection to see them, so the test makes and removes
its own: SCRUM-109's committed planning event plus the safety approval added here.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.security import hash_password
from domain import venue_hold
from domain.event_status import EventStatus
from domain.safety_review import SafetyDecision, fingerprint
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.safety_review import SafetyReview
from models.user import User
from repositories import venue_availability as booking_repo
from services import event_confirmations
from services import safety_reviews as safety_service
from tests.integration.test_cancel_venue_arrangement_races import (
    Committed,
    _commit_planning,
    _finish,
    _in_thread,
    _remove,
    _status_of,
    _wait_until_a_session_waits_for_a_lock,
)
from tests.integration.test_event_confirmation import ready_event, stored_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def _approve_plan(made: Committed, now: datetime) -> uuid.UUID:
    """Commit a Safety Officer approval of the event's plan exactly as it stands."""
    session = SessionLocal()
    try:
        event = session.get(EventRequest, made.event_id)
        assert event is not None
        organiser = session.get(User, event.organiser_id)
        assert organiser is not None
        officer = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=["safety_officer"],
            organisation_id=organiser.organisation_id,
        )
        session.add(officer)
        session.flush()
        plan = safety_service.plan_of(session, event, now)
        safety_service.record(
            session,
            event,
            SafetyDecision.APPROVE,
            "Egress and capacity check out.",
            fingerprint(plan),
            officer.id,
            now,
        )
        session.commit()
        return officer.id
    finally:
        session.close()


def _remove_approval(made: Committed, officer_id: uuid.UUID) -> None:
    """What `_approve_plan` added, removed before the factory removes the rest."""
    session = SessionLocal()
    try:
        session.query(SafetyReview).filter_by(event_request_id=made.event_id).delete()
        session.flush()
        officer = session.get(User, officer_id)
        if officer is not None:
            session.delete(officer)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def held_event() -> Iterator[tuple[Committed, datetime]]:
    """A committed Approved event with one Tentative hold that expires in an hour."""
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    made = _commit_planning((BookingStatus.TENTATIVE,), expires_at)
    yield made, expires_at
    _remove(made)


@pytest.mark.story("SCRUM-80")
def test_when_the_expiry_timer_holds_the_hold_confirmation_waits_then_refuses(
    held_event: tuple[Committed, datetime],
) -> None:
    """The timer locks a due hold first. Confirmation waits for that lock, then reads the
    hold as Expired and refuses. Its own clock is a second earlier, so only the lock can
    make it refuse: without it, it would convert a hold the timer was expiring."""
    made, expires_at = held_event
    (booking_id,) = made.booking_ids
    before = expires_at - timedelta(seconds=1)
    officer_id = _approve_plan(made, before)
    try:
        timer = SessionLocal()
        try:
            [(booking, _event)] = booking_repo.due_holds_for_update(timer, expires_at)
            booking.status = venue_hold.expire(booking.status, booking.expires_at, expires_at)

            def confirm(session: Session) -> object:
                event = session.get(EventRequest, made.event_id)
                assert event is not None
                return event_confirmations.confirm(session, event, made.coordinator_id, before)

            thread, outcome = _in_thread(confirm)
            _wait_until_a_session_waits_for_a_lock()
            timer.commit()
            _finish(thread)
        finally:
            timer.close()

        [refused] = outcome
        assert isinstance(refused, event_confirmations.NotConfirmableError)
        assert _status_of(booking_id).status is BookingStatus.EXPIRED
        check = SessionLocal()
        try:
            event = check.get(EventRequest, made.event_id)
            assert event is not None
            assert (event.status, event.confirmed_at, event.confirmed_by_id) == (
                EventStatus.APPROVED,
                None,
                None,
            )
        finally:
            check.close()
    finally:
        _remove_approval(made, officer_id)


@pytest.mark.story("SCRUM-80")
async def test_confirmation_does_not_reopen_suspended_registration(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC11: intake suspended during replanning stays suspended after confirmation. Only
    the Organiser reopens it (SCRUM-113 AC5)."""
    event, _booking, coordinator = ready_event(db, make_user)
    suspended_at = datetime.now(UTC) - timedelta(hours=1)
    event.registration_opened_at = suspended_at - timedelta(days=1)
    event.registration_suspended_at = suspended_at
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(f"/api/event-requests/{event.id}/confirm")

    assert response.status_code == 200, response.text
    db.expire_all()
    stored = stored_event(db, event.id)
    assert stored.status is EventStatus.CONFIRMED
    assert stored.registration_suspended_at == suspended_at
    assert stored.registration_closed_at is None
