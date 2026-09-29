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
