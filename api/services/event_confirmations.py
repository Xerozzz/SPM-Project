"""The assigned Coordinator confirms an event (SCRUM-80).

One job, and it is the moment an event stops being provisional: the holds Venue Staff
placed become real bookings and preparation can begin.

Everything about *whether* it may happen lives in `domain.event_confirmation`, which in
turn reuses SCRUM-79's arrangement rule rather than restating it. This module decides
where the parts come from, reads ADR-0030's expiry against a real clock, and performs
the change.

The change is one transaction on purpose (AC4, AC5). An event whose status says
Confirmed while one of its holds is still Tentative — or worse, has expired — would be
an event nobody can trust, and no later sweep would repair it. So the prerequisites are
checked under a row lock, every hold is converted, the status moves, and it all commits
together or none of it does.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain import event_status
from domain.event_confirmation import (
    ConfirmationProblems,
    SafetyStanding,
    problems,
)
from domain.safety_review import STANDING_STATUSES, SafetyDecision
from domain.venue_booking import BookingStatus
from domain.venue_hold import confirm as confirm_hold
from models.event_request import EventRequest
from models.venue_booking import VenueBooking
from repositories import event_requests as event_repo
from repositories import safety_reviews as safety_repo
from repositories import venue_availability as booking_repo
from services import safety_reviews as safety_service
from services import venue_buffer_review


class ConfirmationError(Exception):
    """Base class for every refusal this service raises."""


class NotConfirmableError(ConfirmationError):
    """AC2, AC3, AC7 and AC10: something still stands in the way, with the reasons."""

    def __init__(self, found: ConfirmationProblems) -> None:
        super().__init__("the event cannot be confirmed yet")
        self.problems = found


def standing_of(db: Session, event: EventRequest) -> SafetyStanding | None:
    """AC2: the latest safety decision on this event, and the plan it judged.

    `None` when none has ever been recorded. Only the latest counts: an approval that
    follows a rejection is the answer, and a rejection that follows an approval spends
    it (SCRUM-79 AC5).
    """
    history = safety_repo.list_for_event(db, event.id)
    if not history:
        return None
    latest = history[-1]
    return SafetyStanding(
        decision=SafetyDecision(latest.decision),
        plan_fingerprint=latest.plan_fingerprint,
    )


def _needing_attention(db: Session, event: EventRequest, now: datetime) -> set[uuid.UUID]:
    """AC3: the event's standing arrangements Venue Staff have flagged.

    The same derived answer SCRUM-89's list and SCRUM-116's replacement check use, so the
    three cannot disagree about what "needs attention" means. A closure or a buffer
    change can leave a hold clashing while it is still Tentative and unexpired, which is
    precisely the case nothing about the row's status would reveal.
    """
    standing = [
        booking
        for booking in booking_repo.list_bookings_for_event(db, event.id)
        if booking.status in STANDING_STATUSES
    ]
    if not standing:
        return set()
    return set(venue_buffer_review.problems_by_booking(db, standing, now))


def readiness(db: Session, event: EventRequest, now: datetime) -> ConfirmationProblems:
    """What still stands between this event and confirmation, for the screen to show.

    A read, so it takes no lock. The answer is a moment old by the time anyone acts on
    it, which is exactly why `confirm` asks again under a lock rather than trusting it.
    """
    plan = safety_service.plan_of(db, event, now)
    return problems(event.status, plan, standing_of(db, event), _needing_attention(db, event, now))


def current_plan_readiness(db: Session, event: EventRequest, now: datetime) -> ConfirmationProblems:
    """The live confirmation prerequisites without its planning-status requirement."""
    plan = safety_service.plan_of(db, event, now)
    from domain.event_confirmation import current_plan_problems

    return current_plan_problems(plan, standing_of(db, event), _needing_attention(db, event, now))


def confirm(db: Session, event: EventRequest, actor_id: uuid.UUID, now: datetime) -> EventRequest:
    """AC4: commit the event and its holds, or change nothing at all.

    The prerequisites are rechecked here against the locked row rather than trusted from
    whatever the screen last saw (AC7, AC11): a hold can expire, a requirement can be
    added and a safety approval can be spent between loading a page and pressing a
    button, and any of those must refuse rather than confirm something nobody checked.
    """
    locked = event_repo.get_for_update(db, event.id)
    assert locked is not None
    # AC8 and AC11: lock the bookings before judging them, so the ADR-0030 sweep cannot
    # expire a hold between the check and the conversion. The sweep takes the same lock,
    # so one of the two waits and then reads what the other committed.
    booking_repo.lock_bookings_for_event(db, locked.id)

    found = readiness(db, locked, now)
    if found.blocked:
        raise NotConfirmableError(found)

    # AC4: the live holds become bookings. Only Tentative rows are touched, so a
    # booking already Confirmed is left exactly as it is (AC9: unaffected confirmed
    # bookings remain intact) and a rejected or swept row stays the history it is
    # (AC10: superseded bookings are not current requirements).
    for booking in booking_repo.list_bookings_for_event(db, locked.id):
        if booking.status is BookingStatus.TENTATIVE:
            booking.status = confirm_hold(booking.status, booking.expires_at, now)

    locked.status = event_status.confirm(locked.status)
    locked.confirmed_by_id = actor_id
    locked.confirmed_at = now

    db.commit()
    db.refresh(locked)
    return locked


def confirmed_bookings_of(db: Session, event: EventRequest) -> list[VenueBooking]:
    """The event's arrangements after confirmation, for the response to report."""
    return [
        booking
        for booking in booking_repo.list_bookings_for_event(db, event.id)
        if booking.status is BookingStatus.CONFIRMED
    ]
