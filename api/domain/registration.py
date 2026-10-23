"""Registration vocabulary shared by attendee intake and later decisions."""

from enum import StrEnum


class RegistrationStatus(StrEnum):
    PENDING = "pending"
    WAITLISTED = "waitlisted"
    ACCEPTED = "accepted"
    WITHDRAWN = "withdrawn"
    CANCELLED = "cancelled"


LIVE_STATUSES = frozenset(
    {RegistrationStatus.PENDING, RegistrationStatus.WAITLISTED, RegistrationStatus.ACCEPTED}
)
