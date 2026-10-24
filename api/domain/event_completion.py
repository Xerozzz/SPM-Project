"""Completing an event and keeping its closure record (SCRUM-86). Pure, no database.

The assigned Coordinator completes a Confirmed event once it has ended, and records what
actually happened: how many came and any operational notes or issues. Completed is
terminal (`domain.event_status`). The closure record is kept as versions, so a later
correction adds a version and never overwrites who said what before (AC5, ADR-0059).
"""

from datetime import datetime
from enum import StrEnum

from domain.event_status import EventStatus
from domain.validation import FieldProblem

#: The longest closure note accepted, the same cap as other free-text reasons.
NOTES_MAX_LENGTH = 4000


class CompletionRefusal(StrEnum):
    """AC1 and AC6: why this event cannot be completed now."""

    ALREADY_COMPLETED = "already_completed"
    NOT_CONFIRMED = "not_confirmed"
    NOT_ENDED = "not_ended"


def completion_refusal(
    status: EventStatus, end_at: datetime | None, now: datetime
) -> CompletionRefusal | None:
    """None when the event may be completed at `now`, otherwise why not.

    At or after the recorded end time counts (AC1). An event with no end time has not
    provably ended, so it is refused the same way.
    """
    if status is EventStatus.COMPLETED:
        return CompletionRefusal.ALREADY_COMPLETED
    if status is not EventStatus.CONFIRMED:
        return CompletionRefusal.NOT_CONFIRMED
    if end_at is None or now < end_at:
        return CompletionRefusal.NOT_ENDED
    return None


def closure_problems(actual_attendance: int | None, notes: str | None) -> list[FieldProblem]:
    """AC3: attendance is a non-negative whole number or left out, notes are bounded.

    None and 0 are different answers: None means nobody recorded a count.
    """
    problems: list[FieldProblem] = []
    if actual_attendance is not None and actual_attendance < 0:
        problems.append(FieldProblem("actual_attendance", "must be zero or more"))
    if notes is not None and len(notes) > NOTES_MAX_LENGTH:
        problems.append(FieldProblem("notes", f"must be at most {NOTES_MAX_LENGTH} characters"))
    return problems


def clean_notes(notes: str | None) -> str | None:
    """Blank notes are no notes."""
    if notes is None or not notes.strip():
        return None
    return notes.strip()


def may_read_closure(
    *, is_owner: bool, is_assigned: bool, is_lead: bool, is_participating_staff: bool
) -> bool:
    """AC4: the owner, the current assignee, any Lead, and staff who took part.

    "Took part" is decided by the caller from the event's own records. A Coordinator who
    used to be assigned gets nothing from that alone.
    """
    return is_owner or is_assigned or is_lead or is_participating_staff
