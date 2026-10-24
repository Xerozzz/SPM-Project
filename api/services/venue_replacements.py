"""Adopt a linked replacement venue request (SCRUM-133, ADR-0057).

The assigned Coordinator adopts a replacement Venue Staff have approved. The original
arrangement is cancelled through SCRUM-109's own staged cancellation, the replacement
records who adopted it and when, and the link between the two stays. It all commits
together or not at all. The event's status is never touched, so adopting does not
reconfirm anything (SCRUM-79 and SCRUM-80 do that).
"""

import uuid
from datetime import datetime

from core.database import Session
from domain.venue_replacement import AdoptionRefusal, adoption_refusal
from models.venue_booking import VenueBooking
from repositories import event_requests as event_repo
from repositories import venue_availability as booking_repo
from services.venue_bookings import BookingNotFoundError, stage_cancellation

#: Stored as the original's cancellation reason, which SCRUM-109 requires.
ADOPTION_REASON = "Replaced by an adopted replacement venue request"


class AdoptionRefusedError(Exception):
    """AC2: the request is not a replacement, or Venue Staff have not approved it."""

    def __init__(self, refusal: AdoptionRefusal) -> None:
        super().__init__(f"cannot adopt this request: {refusal}")
        self.refusal = refusal


def adopt(
    db: Session,
    event_id: uuid.UUID,
    replacement_id: uuid.UUID,
    coordinator_id: uuid.UUID,
    now: datetime,
) -> VenueBooking:
    """AC1 to AC4. The caller has already checked the actor (CANCEL_VENUE_ARRANGEMENT).

    The event is locked first and then the replacement, so two adoptions of the same
    replacement queue up and the second finds it adopted. Adopting again returns the
    replacement as it is, with no second cancellation and no new record (AC4).
    """
    event = event_repo.get_for_update(db, event_id)
    if event is None:
        raise BookingNotFoundError
    replacement = booking_repo.get_booking_for_update(db, replacement_id)
    if replacement is None or replacement.event_request_id != event.id:
        raise BookingNotFoundError
    if replacement.adopted_at is not None:
        return replacement
    original_id = replacement.replaces_booking_id
    refusal = adoption_refusal(original_id, replacement.status, replacement.expires_at, now)
    if refusal is not None:
        raise AdoptionRefusedError(refusal)
    assert original_id is not None  # adoption_refusal refuses a request replacing nothing
    # SCRUM-109 refuses an event outside planning and an original that is no longer live,
    # and leaves every other arrangement of the event alone (AC1).
    stage_cancellation(db, event.id, original_id, coordinator_id, ADOPTION_REASON, now)
    replacement.adopted_by_id = coordinator_id
    replacement.adopted_at = now
    return booking_repo.save_booking(db, replacement)
