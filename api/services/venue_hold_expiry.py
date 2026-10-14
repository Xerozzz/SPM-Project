"""Expire tentative venue holds whose time has run out, and tell the Coordinator (SCRUM-108).

Run by the minute timer in core/hold_expiry.py, and at the start of placing a hold or
approving a booking, so those always see holds that have run out as expired (ADR-0030).
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain import venue_hold
from domain.notifications import NotificationSource, NotificationType
from repositories import notifications as notification_repo
from repositories import venue_availability as booking_repo


def expire_due_holds(db: Session, now: datetime) -> list[uuid.UUID]:
    """AC1 to AC3: every tentative hold whose expiry is at or before `now` becomes Expired.

    The row is kept with its expiry, holder and time (AC2), and the event is not touched,
    so it is neither cancelled nor deleted. The event's assigned Coordinator is notified in
    the same commit (AC3). The notification is keyed on the booking, so the Coordinator
    gets exactly one per hold even if this runs twice. Returns the expired bookings' ids.
    """
    expired: list[uuid.UUID] = []
    for booking, event in booking_repo.due_holds_for_update(db, now):
        booking.status = venue_hold.expire(booking.status, booking.expires_at, now)
        if event.coordinator_id is not None:
            assert booking.expires_at is not None  # is_due guarantees it
            notification_repo.stage(
                db,
                recipient_id=event.coordinator_id,
                event_request_id=event.id,
                type=NotificationType.VENUE_HOLD_EXPIRED,
                source_type=NotificationSource.VENUE_BOOKING,
                source_id=str(booking.id),
                occurred_at=booking.expires_at,
            )
        expired.append(booking.id)
    db.commit()
    return expired
