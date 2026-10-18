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
    # SCRUM-96: an event request was submitted unassigned and needs Lead triage.
    UNASSIGNED_SUBMISSION = "unassigned_submission"
    # SCRUM-102 AC3: the request was assigned or reassigned — the type names which,
    # so a recipient can tell without opening the event.
    COORDINATOR_ASSIGNED = "coordinator_assigned"
    COORDINATOR_REASSIGNED = "coordinator_reassigned"
    # SCRUM-94: the request was approved or rejected — the type names the decision,
    # so the owning organiser can tell without opening the event.
    REQUEST_APPROVED = "request_approved"
    REQUEST_REJECTED = "request_rejected"


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
    # SCRUM-96: the source is the submission of one event request — the request id
    # is the source_id, so retrying the same submission collides (idempotent) while
    # a later submission of a different request stays distinct.
    EVENT_SUBMISSION = "event_submission"
    # SCRUM-102: one assignment-history row, so retrying the same assignment action
    # collides per recipient while a later reassignment (a new history row) stays
    # distinct. The history row id is the source_id.
    COORDINATOR_ASSIGNMENT = "coordinator_assignment"
    # SCRUM-94: the decision on one event request — the request id is the source_id,
    # so retrying the same decision collides (idempotent). A later decision on the
    # same request (reject, resubmit, reject again) is a new decision with a new
    # decision time, so the source_id carries the decision time to stay distinct.
    EVENT_DECISION = "event_decision"
