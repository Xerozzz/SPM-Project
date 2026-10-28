"""One event's history for the people allowed to read it (SCRUM-88, ADR-0062).

Reads the records the earlier stories keep and hands them to `domain.event_history`.
Nothing here creates, changes or deletes a row, and nothing commits (AC5).
"""

from sqlalchemy.orm import Session

from domain.event_history import HistoryEntry, timeline
from models.event_request import EventRequest
from repositories import event_history as repo


def history_of(
    db: Session, event: EventRequest, may_read_clarifications: bool
) -> list[HistoryEntry]:
    """Every recorded action on `event`, oldest first.

    The caller has passed require_event_access(READ_EVENT_HISTORY), which loaded the
    event. `may_read_clarifications` is the SCRUM-106 rule for this caller: without it,
    note entries are left out entirely (ADR-0036).
    """
    bookings = repo.booking_records(db, event.id)
    booking_ids = [b.id for b in bookings]
    replans = repo.replan_records(db, event.id)
    return timeline(
        repo.request_record(db, event.id),
        repo.assignment_records(db, event.id),
        repo.clarification_records(db, event.id),
        bookings,
        may_read_clarifications,
        repo.buffer_change_records(db, booking_ids),
        repo.requirement_change_records(db, event.id),
        repo.reservation_records(db, event.id),
        replans,
        # SCRUM-120: only an event that went back to planning has causes to match.
        repo.replan_cause_records(db, event.id, booking_ids) if replans else [],
        repo.change_request_records(db, event.id),
        repo.closure_note_records(db, event.id),
    )
