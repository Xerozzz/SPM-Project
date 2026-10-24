"""The hold status for a venue booking. One closed list, so a typo is an error.

Stored in `venue_bookings.status` as its lowercase value and carried through the
search path as this enum (never a bare string), so the repository query and the
domain rule cannot disagree on what blocks search. Mirrors `domain/roles.py` and
`domain/event_status.py`.
"""

from enum import StrEnum


class BookingStatus(StrEnum):
    """Every status a venue booking can be in. Stored as its lowercase value."""

    CONFIRMED = "confirmed"
    PENDING = "pending"
    REJECTED = "rejected"
    # SCRUM-73 AC4: named so the conflict rule can prove a cancelled hold never blocks.
    # SCRUM-109 sets it: the assigned Coordinator cancels one arrangement
    # (domain.venue_cancellation, ADR-0056). Stored in the non-native VARCHAR enum.
    CANCELLED = "cancelled"
    # SCRUM-83: Venue Staff hold a pending request's venue until an expiry (ADR-0029).
    TENTATIVE = "tentative"
    # SCRUM-108: a hold whose expiry passed before it was approved. Kept for its history,
    # and like rejected or cancelled it no longer holds the venue (ADR-0030).
    EXPIRED = "expired"


class InvalidBookingTransitionError(Exception):
    """The booking is not in a status that allows the requested change."""

    def __init__(self, current: BookingStatus, target: BookingStatus) -> None:
        super().__init__(f"cannot move a venue booking from {current} to {target}")
        self.current = current
        self.target = target


def approve(current: BookingStatus) -> BookingStatus:
    """SCRUM-110 (superseding SCRUM-74's direct confirmation): approving a pending
    request creates a time-limited tentative hold, never a confirmation. The expiry is
    validated separately by `domain.venue_hold.expiry_problems`; this only moves the
    status, so a second approval of the same row is refused after the row lock."""
    if current is not BookingStatus.PENDING:
        raise InvalidBookingTransitionError(current, BookingStatus.TENTATIVE)
    return BookingStatus.TENTATIVE


def hold(current: BookingStatus) -> BookingStatus:
    """SCRUM-83 AC1: only a pending request can be put on a tentative hold. A request that
    is already held, decided or cancelled is refused, so a hold is never placed twice."""
    if current is not BookingStatus.PENDING:
        raise InvalidBookingTransitionError(current, BookingStatus.TENTATIVE)
    return BookingStatus.TENTATIVE
