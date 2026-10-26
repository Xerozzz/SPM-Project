"""Reminder schedule persistence (SCRUM-85)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_reminder import REMINDABLE_STATUSES
from models.event_reminder import EventReminder
from models.event_request import EventRequest


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventReminder]:
    """AC2: this event's schedule, soonest lead time last so it reads as a timeline."""
    statement = (
        select(EventReminder)
        .where(EventReminder.event_request_id == event_request_id)
        .order_by(EventReminder.lead_minutes.desc())
    )
    return list(db.scalars(statement))


def lock_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventReminder]:
    """The schedule, locked, so an edit and the sweep cannot interleave.

    AC6: a schedule change must not resend a delivered occurrence. Without this an edit
    could delete a row the sweep had already picked up and was about to mark processed,
    and the next edit would recreate it as unprocessed.
    """
    statement = (
        select(EventReminder)
        .where(EventReminder.event_request_id == event_request_id)
        .order_by(EventReminder.lead_minutes)
        .with_for_update()
    )
    return list(db.scalars(statement))


def due_candidates_for_update(
    db: Session, now: datetime
) -> list[tuple[EventReminder, EventRequest]]:
    """Unprocessed reminders on events that could still have one, with their event.

    Narrowed in SQL to what is cheap and certain — unprocessed, the event still upcoming
    and in a phase that has arrangements to chase — and then judged row by row by
    `domain.event_reminder.may_process`. The lead time is deliberately not turned into
    interval arithmetic here: the rule that decides whether an occurrence is due belongs
    in the domain, where it is tested without a database, and the candidate set is
    bounded by the events actually being planned.

    `SKIP LOCKED` means two workers never wait on each other or process the same
    occurrence twice (AC6); a row one of them holds is simply left to that one.
    """
    statement = (
        select(EventReminder, EventRequest)
        .join(EventRequest, EventRequest.id == EventReminder.event_request_id)
        .where(
            EventReminder.processed_at.is_(None),
            EventRequest.status.in_(REMINDABLE_STATUSES),
            EventRequest.start_at.is_not(None),
            EventRequest.start_at > now,
        )
        .order_by(EventReminder.lead_minutes.desc(), EventReminder.id)
        .with_for_update(skip_locked=True, of=EventReminder)
    )
    return list(db.execute(statement).tuples())
