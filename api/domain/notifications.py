"""Notification vocabulary for the in-app inbox (SCRUM-99).

Pure: no I/O, no ORM imports. The type list is finite and stored as stable string
values; later trigger stories (SCRUM-96, SCRUM-102, SCRUM-95, SCRUM-94) add their
types here without changing the storage shape. See ADR-0022.
"""

from enum import StrEnum


class NotificationType(StrEnum):
    """What triggered a notification. Stored as its lowercase value."""

    # SCRUM-99 seeds the vocabulary with a generic placeholder so the inbox,
    # repository, and API can land before the first business trigger. Trigger
    # stories replace direct use of this with their own specific types.
    GENERAL = "general"
    # SCRUM-108 AC3: the venue hold for one of your events has expired.
    VENUE_HOLD_EXPIRED = "venue_hold_expired"


class NotificationSource(StrEnum):
    """What business record a notification was raised from. Stored as its value.

    Event ID alone cannot deduplicate: one event receives many clarifications and
    assignment changes. The (source_type, source_id) pair names the exact action —
    e.g. one clarification message, one assignment-history row — so retrying the
    same action collides (idempotent) while distinct actions stay distinct.
    """

    GENERAL = "general"
    # SCRUM-108: one venue booking row, so each expired hold notifies exactly once.
    VENUE_BOOKING = "venue_booking"
