"""Reminders about arrangements still outstanding before an event (SCRUM-85).

Two jobs: keeping the Coordinator's schedule, and processing the occurrences that fall
due.

The second one asks `services.event_confirmations.readiness` what is outstanding rather
than working it out again. That is the ticket's instruction — "read the merged
authoritative state rather than introducing a second readiness calculation" — and it is
also the only way AC4 can stay true for free: "retained historical superseded
arrangements do not create false reminders" is SCRUM-80's `STANDING_STATUSES` rule, and
"action-required venues" is the needs-attention check added with it. A copy of that logic
here would be a second place for it to drift.

Nothing is sent twice. An occurrence is a row, processing locks it with `SKIP LOCKED`,
and the row is marked processed in the same transaction as the notification it raised —
so a retry finds it done, a second worker never sees it, and a failure leaves it
undelivered rather than silently marked sent (AC6, AC8).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from domain.event_reminder import (
    ReminderOutcome,
    due_at,
    lead_time_problems,
    may_process,
    outcome_of,
    retained,
    whole_minutes,
)
from domain.notifications import NotificationSource, NotificationType
from domain.validation import FieldProblem
from models.event_reminder import EventReminder
from models.event_request import EventRequest
from repositories import event_reminders as repo
from repositories import notifications as notifications_repo
from services import event_confirmations as confirmation_service

logger = logging.getLogger(__name__)


class InvalidReminderScheduleError(Exception):
    """AC1: the schedule was refused, with every reason and nothing changed."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid reminder schedule")
        self.problems = problems


@dataclass(frozen=True)
class ProcessedOccurrence:
    """What one due occurrence did, for the caller to log and for tests to assert."""

    reminder_id: uuid.UUID
    event_request_id: uuid.UUID
    lead_minutes: int
    outcome: ReminderOutcome


def list_for_event(db: Session, event: EventRequest) -> list[EventReminder]:
    """AC2: the schedule as it stands."""
    return repo.list_for_event(db, event.id)


def configure(
    db: Session,
    event: EventRequest,
    lead_minutes: list[object],
    actor_id: uuid.UUID,
    now: datetime,
) -> list[EventReminder]:
    """AC1 and AC6: replace the schedule, keeping what each kept lead time has done.

    Validated before anything is touched, so a list with one bad entry leaves the stored
    schedule exactly as it was (AC1: "without partial changes").

    A lead time the Coordinator keeps keeps its row, and with it the record that its
    occurrence was already processed. Rebuilding the schedule on every edit would forget
    that and send the same reminder a second time, which AC6 forbids. A lead time that is
    removed loses that history; adding it back later is a deliberate re-arming rather
    than an accident, because the Coordinator had to ask for it twice.
    """
    problems = lead_time_problems(lead_minutes)
    if problems:
        raise InvalidReminderScheduleError(problems)

    wanted = whole_minutes(lead_minutes)
    existing = repo.lock_for_event(db, event.id)
    keep = retained((row.lead_minutes for row in existing), wanted)

    for row in existing:
        if row.lead_minutes not in keep:
            db.delete(row)
    for value in wanted:
        if value not in keep:
            db.add(
                EventReminder(
                    event_request_id=event.id,
                    lead_minutes=value,
                    created_by_id=actor_id,
                    created_at=now,
                )
            )
    db.commit()
    return repo.list_for_event(db, event.id)


def process_due(db: Session, now: datetime) -> list[ProcessedOccurrence]:
    """AC3 to AC8: every occurrence that has fallen due, processed exactly once.

    Each row is judged by the pure rule, and only then does the expensive part run: what
    is outstanding is asked of the existing readiness, not recalculated.

    `processed_at` is set whether or not a reminder was created. An occurrence that found
    nothing outstanding is still *processed* — leaving it open would mean re-evaluating
    it on every tick for the rest of the event's life, and sending a reminder the moment
    anything slipped, long after the time the Coordinator actually asked for (AC7).
    """
    done: list[ProcessedOccurrence] = []
    for reminder, event in repo.due_candidates_for_update(db, now):
        if not may_process(
            event.status,
            event.start_at,
            reminder.lead_minutes,
            reminder.processed_at is not None,
            now,
        ):
            continue

        try:
            outstanding = confirmation_service.readiness(db, event, now).blocked
        except Exception:
            # One event whose plan cannot be read must not starve every other event's
            # reminders. The batch below would roll back for all of them, every tick,
            # for as long as the bad data lasted. This occurrence stays unprocessed and
            # is retried next tick; nothing has been staged for it yet, so there is
            # nothing half-done to undo (AC8).
            logger.exception("reading readiness for event %s failed", event.id)
            continue

        outcome = outcome_of(outstanding)
        assert event.start_at is not None  # may_process refuses an event without one
        if outcome is ReminderOutcome.NOTIFIED and event.coordinator_id is not None:
            # AC5: addressed to the *current* assignee, which is what AC2 means by
            # reassignment transferring access — the new Coordinator owns the work now.
            # The occurrence time, not `now`, so a catch-up run still reports the moment
            # the Coordinator asked about. ADR-0022 keeps presentation out of the row:
            # which arrangements are outstanding is read live from the event, so the
            # reminder can never disagree with what the event's own screen shows.
            notifications_repo.stage(
                db,
                recipient_id=event.coordinator_id,
                event_request_id=event.id,
                type=NotificationType.ARRANGEMENTS_INCOMPLETE,
                source_type=NotificationSource.EVENT_REMINDER,
                source_id=str(reminder.id),
                occurred_at=due_at(event.start_at, reminder.lead_minutes),
            )
        reminder.processed_at = now
        done.append(
            ProcessedOccurrence(
                reminder_id=reminder.id,
                event_request_id=event.id,
                lead_minutes=reminder.lead_minutes,
                outcome=outcome,
            )
        )

    # One commit for the batch: each row's notification and its processed mark land
    # together, so a failure anywhere leaves every occurrence in this run undelivered
    # and unprocessed rather than half done (AC8).
    db.commit()
    return done
