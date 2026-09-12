"""The roles a user can hold. One closed list, so a typo is an error rather than a silent 403.

Stored in `users.roles` and carried in the JWT `roles` claim as the lowercase values below;
the frontend compares against the same strings (`hasRole('organiser')`).
"""

from enum import StrEnum


class Role(StrEnum):
    ORGANISER = "organiser"
    COORDINATOR = "coordinator"
    VENUE_STAFF = "venue_staff"
    TECH_SUPPORT = "tech_support"
    ATTENDEE = "attendee"
