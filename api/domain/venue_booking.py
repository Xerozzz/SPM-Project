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
    # Nothing sets it yet; no migration needed (status is a non-native VARCHAR enum).
    CANCELLED = "cancelled"


class InvalidBookingTransitionError(Exception):
    """The booking is not in a status that allows the requested change."""

    def __init__(self, current: BookingStatus, target: BookingStatus) -> None:
        super().__init__(f"cannot move a venue booking from {current} to {target}")
        self.current = current
        self.target = target


def approve(current: BookingStatus) -> BookingStatus:
    """SCRUM-74 (absorbing SCRUM-40's approve action): only a pending request can be
    confirmed. A second approval of the same booking, after the row lock has made it wait
    for the first, sees CONFIRMED here and is refused."""
    if current is not BookingStatus.PENDING:
        raise InvalidBookingTransitionError(current, BookingStatus.CONFIRMED)
    return BookingStatus.CONFIRMED
