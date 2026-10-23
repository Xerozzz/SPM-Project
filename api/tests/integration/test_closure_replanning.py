"""SCRUM-132: a venue closure returns the Confirmed events it affects to planning."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from domain.registration import RegistrationStatus
from domain.venue_unavailability import VenueUnavailabilityFields
from models.event_registration import EventRegistration
from models.event_request import EventRequest
from models.safety_review import SafetyReview
from models.user import User
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability
from repositories import safety_reviews as safety_repo
from services import event_registrations
from services import registration_intake as intake_service
from services import venue_unavailabilities as closures
from tests.integration.test_event_confirmation import ready_event
from tests.integration.test_intake_suspension_on_replan import _register
from tests.integration.test_safety_approval_invalidation import _confirmed
from tests.integration.test_safety_review import _NOW
from tests.integration.test_submit_event_request import MakeUser

_LATER = _NOW + timedelta(minutes=5)


def _over(booking: VenueBooking, shift: timedelta = timedelta()) -> VenueUnavailabilityFields:
    """A closure over the booking's own hours, moved by `shift`."""
    return VenueUnavailabilityFields(
        starts_at=booking.start_at + shift,
        ends_at=booking.end_at + shift,
        reason="Burst pipe",
    )


def _close(
    db: Session, booking: VenueBooking, staff: User, at: datetime = _NOW, **kw: timedelta
) -> VenueUnavailability:
    return closures.create(db, booking.venue_id, _over(booking, **kw), staff.id, at).record


def _event(db: Session, event: EventRequest) -> EventRequest:
    db.expire_all()
    stored = db.get(EventRequest, event.id)
    assert stored is not None
    return stored


def _approval(db: Session, event: EventRequest) -> SafetyReview:
    return safety_repo.list_for_event(db, event.id)[-1]


def _open_intake(db: Session, event: EventRequest) -> None:
    event.registration_opened_at = _NOW
    event.registration_closes_at = _NOW + timedelta(days=1)
    db.flush()


@pytest.mark.story("SCRUM-132")
def test_a_closure_returns_a_confirmed_event_to_planning(db: Session, make_user: MakeUser) -> None:
    event, booking, _ = _confirmed(db, make_user)
    _open_intake(db, event)

    _close(db, booking, make_user("venue_staff"))

    stored = _event(db, event)
    assert stored.status is EventStatus.APPROVED
    assert stored.registration_suspended_at == _NOW
    assert stored.registration_closes_at == _NOW + timedelta(days=1)
    approval = _approval(db, event)
    assert (approval.invalidated_at, approval.invalidation_cause) == (_NOW, "venue_closure")


@pytest.mark.story("SCRUM-132")
def test_a_closure_keeps_existing_registrations_and_refuses_new_ones(
    db: Session, make_user: MakeUser
) -> None:
    """AC1 with real SCRUM-42 registrations."""
    event, booking, _ = _confirmed(db, make_user)
    _open_intake(db, event)
    kept = _register(db, event, make_user("attendee"), _NOW)

    _close(db, booking, make_user("venue_staff"))

    db.expire_all()
    stored = db.get(EventRegistration, kept.id)
    assert stored is not None and stored.status is RegistrationStatus.PENDING
    with pytest.raises(event_registrations.RegistrationError):
        _register(db, event, make_user("attendee"), _LATER)


@pytest.mark.story("SCRUM-132")
def test_an_event_already_in_planning_is_left_as_it_is(db: Session, make_user: MakeUser) -> None:
    event, booking, _ = ready_event(db, make_user)

    _close(db, booking, make_user("venue_staff"))

    stored = _event(db, event)
    assert stored.status is EventStatus.APPROVED
    assert stored.registration_suspended_at is None
    assert _approval(db, event).invalidated_at is None


@pytest.mark.story("SCRUM-132")
def test_saving_the_closure_again_does_not_replan_twice(db: Session, make_user: MakeUser) -> None:
    event, booking, _ = _confirmed(db, make_user)
    staff = make_user("venue_staff")
    record = _close(db, booking, staff)

    closures.update(db, booking.venue_id, record.id, _over(booking), staff.id, _LATER)

    stored = _event(db, event)
    assert stored.registration_suspended_at == _NOW
    assert _approval(db, event).invalidated_at == _NOW


@pytest.mark.story("SCRUM-132")
def test_moving_a_closure_onto_a_confirmed_event_replans_it(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, _ = _confirmed(db, make_user)
    staff = make_user("venue_staff")
    record = _close(db, booking, staff, shift=timedelta(days=2))
    assert _event(db, event).status is EventStatus.CONFIRMED

    closures.update(db, booking.venue_id, record.id, _over(booking), staff.id, _LATER)

    assert _event(db, event).status is EventStatus.APPROVED
    assert _approval(db, event).invalidated_at == _LATER


@pytest.mark.story("SCRUM-132")
def test_moving_a_closure_away_does_not_reconfirm(db: Session, make_user: MakeUser) -> None:
    event, booking, _ = _confirmed(db, make_user)
    staff = make_user("venue_staff")
    record = _close(db, booking, staff)

    closures.update(
        db, booking.venue_id, record.id, _over(booking, timedelta(days=2)), staff.id, _LATER
    )

    stored = _event(db, event)
    assert stored.status is EventStatus.APPROVED
    assert stored.registration_suspended_at == _NOW
    assert _approval(db, event).invalidated_at == _NOW


@pytest.mark.story("SCRUM-132")
def test_a_failed_replan_saves_no_part_of_the_closure(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    event, booking, _ = _confirmed(db, make_user)
    staff = make_user("venue_staff")
    db.commit()

    def broken(*_: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(intake_service, "suspend", broken)
    with pytest.raises(RuntimeError):
        _close(db, booking, staff)
    db.rollback()
    monkeypatch.undo()

    stored = _event(db, event)
    assert stored.status is EventStatus.CONFIRMED
    assert _approval(db, event).invalidated_at is None
    saved = select(VenueUnavailability).where(VenueUnavailability.venue_id == booking.venue_id)
    assert list(db.scalars(saved)) == []
