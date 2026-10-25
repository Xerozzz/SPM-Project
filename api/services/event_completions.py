"""Complete an event and keep its closure record (SCRUM-86, ADR-0059).

The assigned Coordinator completes a Confirmed event once it has ended. In one
transaction: open registration intake is closed through SCRUM-113's own staged close,
the status moves to Completed through the shared machine, who and when are recorded, and
the first version of the closure record is written. Bookings, equipment reservations and
registrations are left exactly as they were (AC7).

`completed_by_id` and `completed_at` are the committed source action SCRUM-50
notifies on (AC8), in the same commit.
"""

import uuid
from datetime import datetime

from core.database import Session
from domain import event_status
from domain.event_completion import (
    CompletionRefusal,
    clean_notes,
    closure_problems,
    completion_refusal,
)
from domain.event_status import EventStatus
from domain.registration_intake import intake_is_open
from domain.validation import FieldProblem
from models.event_closure_note import EventClosureNote
from models.event_request import EventRequest
from repositories import event_closures as repo
from repositories import event_requests as event_repo
from services import lifecycle_notifications as lifecycle
from services import registration_intake


class CompletionError(Exception):
    """Base class for every refusal this service raises."""


class NotCompletableError(CompletionError):
    """AC1 and AC6: the event is not Confirmed, has not ended, or is already Completed."""

    def __init__(self, refusal: CompletionRefusal) -> None:
        super().__init__(f"the event cannot be completed: {refusal}")
        self.refusal = refusal


class InvalidClosureError(CompletionError):
    """AC3: the attendance or notes are not acceptable, field by field."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid closure record")
        self.problems = problems


class NotCompletedError(CompletionError):
    """A closure record can only be corrected once the event is Completed."""


def complete(
    db: Session,
    event_id: uuid.UUID,
    actor_id: uuid.UUID,
    actual_attendance: int | None,
    notes: str | None,
    now: datetime,
) -> EventRequest:
    """AC1 to AC3, AC6, AC7. The caller has already checked the actor (COMPLETE_EVENT).

    The event row is locked first, so two completions queue up and the second is told
    the event is already Completed, with no second record (AC6).
    """
    event = _locked(db, event_id)
    refusal = completion_refusal(event.status, event.end_at, now)
    if refusal is not None:
        raise NotCompletableError(refusal)
    _check(actual_attendance, notes)
    # AC2: asked while the event is still Confirmed, since open intake needs that.
    if intake_is_open(event.status, registration_intake.settings_of(event), now):
        registration_intake.close(event, now)
    event.status = event_status.complete(event.status)
    event.completed_by_id = actor_id
    event.completed_at = now
    repo.add_note(db, _note(event.id, 1, actual_attendance, notes, actor_id, now))
    # SCRUM-50 AC7: the Organiser and the Coordinator hear it, in the same commit.
    lifecycle.completed(db, event, now)
    db.commit()
    db.refresh(event)
    return event


def correct(
    db: Session,
    event_id: uuid.UUID,
    actor_id: uuid.UUID,
    actual_attendance: int | None,
    notes: str | None,
    now: datetime,
) -> EventClosureNote:
    """AC5: a correction is a new version. Earlier versions are never changed."""
    event = _locked(db, event_id)
    if event.status is not EventStatus.COMPLETED:
        raise NotCompletedError
    _check(actual_attendance, notes)
    history = repo.notes_for_event(db, event.id)
    version = history[-1].version + 1 if history else 1
    note = repo.add_note(db, _note(event.id, version, actual_attendance, notes, actor_id, now))
    db.commit()
    db.refresh(note)
    return note


def history_of(db: Session, event: EventRequest) -> list[EventClosureNote]:
    """AC4, AC5: every version of the closure record, oldest first."""
    return repo.notes_for_event(db, event.id)


def completed_for_coordinator(db: Session, coordinator_id: uuid.UUID) -> list[EventRequest]:
    """The current assignee's Completed events, newest first."""
    return repo.list_completed_for_coordinator(db, coordinator_id)


def _check(actual_attendance: int | None, notes: str | None) -> None:
    problems = closure_problems(actual_attendance, notes)
    if problems:
        raise InvalidClosureError(problems)


def _note(
    event_id: uuid.UUID,
    version: int,
    actual_attendance: int | None,
    notes: str | None,
    actor_id: uuid.UUID,
    now: datetime,
) -> EventClosureNote:
    return EventClosureNote(
        event_request_id=event_id,
        version=version,
        actual_attendance=actual_attendance,
        notes=clean_notes(notes),
        recorded_by_id=actor_id,
        recorded_at=now,
    )


def _locked(db: Session, event_id: uuid.UUID) -> EventRequest:
    event = event_repo.get_for_update(db, event_id)
    if event is None:
        raise NotCompletedError
    return event
