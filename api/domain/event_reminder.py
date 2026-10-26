"""When an arrangement reminder is due, and what a valid schedule looks like (SCRUM-85).

Pure, no database and no clock of its own.

The Coordinator sets lead times in whole minutes before the event starts: "an hour
before", "a day before". Each one is an *occurrence*, and an occurrence is processed at
most once (AC6), which is why identity here is the schedule row rather than the moment —
moving the event moves the moment, and a reminder already sent is history, not something
to send again (AC8).

What counts as *incomplete* is deliberately not here. AC3 and AC4 describe exactly what
`domain.event_confirmation` already decides for SCRUM-80, and the ticket is explicit that
this story reads the merged authoritative state rather than introducing a second
readiness calculation. So the rules in this module answer only "is this occurrence due,
and may it be processed", and the caller asks the existing rule what is missing.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from domain.event_status import EventStatus
from domain.validation import FieldProblem

#: AC1: the field a schedule problem is reported against, so one 422 body covers a list.
LEAD_TIMES_FIELD = "lead_minutes"

#: A year of lead time. Not a rule the customer gave, but an unbounded integer here
#: becomes a due time far outside any range the database can hold, and "500 years before"
#: is a typo rather than an intention.
MAX_LEAD_MINUTES = 525_600


class ReminderOutcome(StrEnum):
    """What processing one due occurrence did, for the caller to record and report."""

    #: Work was outstanding, so the Coordinator was told (AC5).
    NOTIFIED = "notified"
    #: Nothing was outstanding, so no reminder was created (AC5) — but the occurrence is
    #: still processed, so it cannot fire again every minute afterwards (AC7).
    NOTHING_OUTSTANDING = "nothing_outstanding"


def lead_time_problems(lead_minutes: Sequence[object]) -> list[FieldProblem]:
    """AC1: why this schedule cannot be saved, or nothing if it can.

    Every reason at once and the schedule is saved only if there are none, which is what
    AC1 means by refusing "without partial changes": a list with one bad entry leaves the
    stored schedule exactly as it was rather than saving the good ones.

    Takes `object` rather than `int` on purpose: the values arrive from a request body,
    and the whole job of this function is to say which of them are not whole positive
    minutes. Typing the parameter as `int` would assert the very thing being checked.
    """
    problems: list[FieldProblem] = []
    for value in lead_minutes:
        # bool is an int subclass; True would otherwise read as "one minute before".
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(FieldProblem(LEAD_TIMES_FIELD, "must be whole minutes"))
        elif value <= 0:
            problems.append(FieldProblem(LEAD_TIMES_FIELD, "must be more than zero minutes"))
        elif value > MAX_LEAD_MINUTES:
            problems.append(
                FieldProblem(LEAD_TIMES_FIELD, "must be within a year of the event start")
            )
    if len(set(lead_minutes)) != len(lead_minutes):
        problems.append(FieldProblem(LEAD_TIMES_FIELD, "must not repeat a lead time"))
    return problems


def whole_minutes(lead_minutes: Sequence[object]) -> list[int]:
    """The schedule as whole minutes, for a caller that has already validated it.

    Narrowing in one place rather than casting at the call site: `lead_time_problems`
    decides what counts as a lead time, so the same two conditions decide what survives
    here. Anything it would have refused is simply not a lead time.
    """
    return [
        value
        for value in lead_minutes
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    ]


def due_at(event_start_at: datetime, lead_minutes: int) -> datetime:
    """The moment this occurrence falls due: that many minutes before the event starts."""
    return event_start_at - timedelta(minutes=lead_minutes)


#: AC7: statuses a reminder is never sent for. Cancelled and Completed are terminal
#: (SCRUM-115, SCRUM-86) so there is nothing left to arrange, and the rest are phases
#: where the Coordinator has no arrangements to chase yet or the request is closed.
REMINDABLE_STATUSES: frozenset[EventStatus] = frozenset({EventStatus.APPROVED})


def may_process(
    status: EventStatus,
    event_start_at: datetime | None,
    lead_minutes: int,
    processed: bool,
    now: datetime,
) -> bool:
    """AC7: may this occurrence be processed right now?

    Due, not processed before, the event still upcoming, and the event in a phase where
    arrangements are still being made. "Still upcoming" is what lets a missed occurrence
    be picked up late — a tick that never ran, or a worker that was down — while the
    single processed flag is what stops that catch-up becoming a burst.

    A Confirmed event is deliberately not remindable: SCRUM-80 refuses to confirm until
    every arrangement and the safety approval are in order, so there is nothing a
    reminder could ask for. That is a statement about arrangements, not a label: it holds
    because confirmation enforced it, not because the word says so.
    """
    if processed or event_start_at is None:
        return False
    if status not in REMINDABLE_STATUSES:
        return False
    if now >= event_start_at:
        return False
    return now >= due_at(event_start_at, lead_minutes)


def outcome_of(incomplete: bool) -> ReminderOutcome:
    """AC5: a reminder is created only when something is actually outstanding."""
    return ReminderOutcome.NOTIFIED if incomplete else ReminderOutcome.NOTHING_OUTSTANDING


def retained(existing: Iterable[int], wanted: Sequence[int]) -> set[int]:
    """AC6: which lead times survive a schedule change, keeping their processed history.

    A lead time the Coordinator keeps must keep its row, because the row is what records
    that its occurrence was already sent. Rebuilding the schedule from scratch on every
    edit would forget that and send the same reminder twice.
    """
    return {value for value in existing if value in set(wanted)}
