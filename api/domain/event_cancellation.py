"""Cancelling a whole event (SCRUM-115). Pure, no database.

The owning Organiser may ask for an active event to be cancelled. The current assigned
Coordinator applies or declines that request, or cancels on their own with a reason.
Cancelled is terminal (`domain.event_status`). Releasing the event's bookings, equipment
and registrations is the service's job, in the same transaction (ADR-0061).
"""

from enum import StrEnum

from domain.event_status import EventStatus
from domain.validation import FieldProblem

#: The longest reason or note accepted, the same cap as other free-text reasons.
TEXT_MAX_LENGTH = 4000


class CancellationRefusal(StrEnum):
    """AC2: why this event cannot be cancelled through this flow."""

    ALREADY_CANCELLED = "already_cancelled"
    COMPLETED = "completed"
    NOT_ACTIVE = "not_active"


class RequestStatus(StrEnum):
    """AC1: where an Organiser's cancellation request stands. Stored as its value."""

    PENDING = "pending"
    APPLIED = "applied"
    DECLINED = "declined"


def cancellation_refusal(status: EventStatus) -> CancellationRefusal | None:
    """None when an event in `status` may be cancelled, otherwise why not.

    Submitted, planning (Approved) and Confirmed events may be. Drafts and Rejected
    requests are not active, so the Organiser deletes or edits them instead.
    """
    if status is EventStatus.CANCELLED:
        return CancellationRefusal.ALREADY_CANCELLED
    if status is EventStatus.COMPLETED:
        return CancellationRefusal.COMPLETED
    if status in (EventStatus.SUBMITTED, EventStatus.APPROVED, EventStatus.CONFIRMED):
        return None
    return CancellationRefusal.NOT_ACTIVE


def text_problems(field: str, text: str | None) -> list[FieldProblem]:
    """AC1, AC3: a reason or note is required. Blank does not count."""
    if text is None or not text.strip():
        return [FieldProblem(field, "is required")]
    if len(text.strip()) > TEXT_MAX_LENGTH:
        return [FieldProblem(field, f"must be at most {TEXT_MAX_LENGTH} characters")]
    return []


def may_read_cancellation(*, is_owner: bool, is_assigned: bool, is_lead: bool) -> bool:
    """AC1: the owner and the current assignee see the requests, and any Lead for
    oversight. A Coordinator who used to be assigned gets nothing from that alone."""
    return is_owner or is_assigned or is_lead
