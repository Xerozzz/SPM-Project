"""Cancel one arrangement of a Confirmed event as a venue change (SCRUM-118, ADR-0066).

A Confirmed event cannot simply lose an arrangement: what was confirmed no longer exists.
So cancelling one is a venue change, which the Coordinator has to confirm, and in the
same transaction the event goes back to planning: Approved again, its safety approval no
longer counting, and new registrations suspended (SCRUM-130, ADR-0052). Each half is the
shared operation, not a copy: SCRUM-109's `stage_cancellation` and the replanning that
change requests and venue closures already use.
"""

import uuid
from datetime import datetime

from core.database import Session
from domain import venue_cancellation
from domain.event_replanning import ReplanCause
from models.event_request import EventRequest
from models.venue_booking import VenueBooking
from repositories import event_requests as event_repo
from services.event_replanning import return_to_planning
from services.venue_bookings import InvalidCancellationError, stage_cancellation


def cancel_for_venue_change(
    db: Session,
    event_id: uuid.UUID,
    booking_id: uuid.UUID,
    coordinator_id: uuid.UUID,
    reason: str | None,
    confirmed: bool,
    now: datetime,
) -> tuple[VenueBooking, EventRequest]:
    """AC2: the arrangement Cancelled and the event back in planning, committed once.

    The caller has already checked the actor (CANCEL_VENUE_ARRANGEMENT). Without the
    Coordinator's confirmation, or without a reason, nothing is read or locked (AC1). The
    event row is locked first and then
    the booking, inside `stage_cancellation`, as SCRUM-109 does (ADR-0056); every refusal
    there is SCRUM-109's own (AC6). The event's other arrangements are not touched (AC5).

    Nothing is committed until both halves have been staged, and any failure rolls both
    back, so the arrangement, the status, the safety approval and intake either all change
    or none do (AC3). The replanning also stages the SCRUM-50 "event replanned" notices,
    as a venue closure does.
    """
    problems = venue_cancellation.venue_change_problems(confirmed, reason)
    if problems:
        raise InvalidCancellationError(problems)
    try:
        booking = stage_cancellation(
            db, event_id, booking_id, coordinator_id, reason, now, venue_change=True
        )
        # Already locked by stage_cancellation in this transaction; this returns that row.
        event = event_repo.get_for_update(db, event_id)
        assert event is not None
        return_to_planning(db, event, ReplanCause.VENUE_CANCELLATION, booking.id, now)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(booking)
    db.refresh(event)
    return booking, event
