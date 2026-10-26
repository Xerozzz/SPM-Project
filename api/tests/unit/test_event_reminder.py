"""SCRUM-85: when an arrangement reminder is due, and what a valid schedule is.

Pure, so every rule gets its own fast test (AGENTS.md section 4). What counts as
incomplete work is not tested here on purpose: AC3 and AC4 are
`domain.event_confirmation`'s rules, tested there, and the ticket is explicit that this
story reads that state rather than calculating readiness a second time.
"""

from datetime import UTC, datetime, timedelta

import pytest

from domain.event_reminder import (
    LEAD_TIMES_FIELD,
    MAX_LEAD_MINUTES,
    ReminderOutcome,
    due_at,
    lead_time_problems,
    may_process,
    outcome_of,
    retained,
    whole_minutes,
)
from domain.event_status import EventStatus

_START = datetime(2030, 3, 4, 10, tzinfo=UTC)


def reasons(values: list[object]) -> list[str]:
    return [problem.reason for problem in lead_time_problems(values)]


@pytest.mark.story("SCRUM-85")
def test_a_schedule_of_whole_positive_minutes_is_accepted() -> None:
    assert lead_time_problems([60, 1440, 10_080]) == []


@pytest.mark.story("SCRUM-85")
def test_zero_and_negative_lead_times_are_refused() -> None:
    """AC1: "before its start" has no meaning for zero or a negative offset."""
    assert reasons([0]) == ["must be more than zero minutes"]
    assert reasons([-30]) == ["must be more than zero minutes"]


@pytest.mark.story("SCRUM-85")
def test_a_fractional_lead_time_is_refused() -> None:
    """AC1. A float would otherwise be truncated into a different schedule silently."""
    assert reasons([90.5]) == ["must be whole minutes"]


@pytest.mark.story("SCRUM-85")
def test_a_boolean_is_not_a_lead_time() -> None:
    """`bool` is an `int` in Python, so `True` would read as "one minute before"."""
    assert reasons([True]) == ["must be whole minutes"]


@pytest.mark.story("SCRUM-85")
def test_a_repeated_lead_time_is_refused() -> None:
    """AC1 asks for distinct lead times: the same reminder twice is not two reminders."""
    assert reasons([60, 60]) == ["must not repeat a lead time"]


@pytest.mark.story("SCRUM-85")
def test_an_absurd_lead_time_is_refused() -> None:
    assert reasons([MAX_LEAD_MINUTES + 1]) == ["must be within a year of the event start"]
    assert lead_time_problems([MAX_LEAD_MINUTES]) == []


@pytest.mark.story("SCRUM-85")
def test_every_problem_is_reported_at_once() -> None:
    """AC1 refuses "without partial changes", so the caller sees the whole list."""
    found = lead_time_problems([0, -1])

    assert [problem.field for problem in found] == [LEAD_TIMES_FIELD, LEAD_TIMES_FIELD]
    assert len(found) == 2


@pytest.mark.story("SCRUM-85")
def test_an_occurrence_falls_due_that_many_minutes_before_the_event() -> None:
    assert due_at(_START, 60) == _START - timedelta(hours=1)


@pytest.mark.story("SCRUM-85")
def test_an_occurrence_is_processed_once_it_falls_due() -> None:
    at_due = _START - timedelta(hours=1)

    assert may_process(EventStatus.APPROVED, _START, 60, False, at_due) is True
    assert may_process(EventStatus.APPROVED, _START, 60, False, at_due - timedelta(minutes=1)) is (
        False
    )


@pytest.mark.story("SCRUM-85")
def test_an_occurrence_already_processed_is_never_processed_again() -> None:
    """AC6: at most one per occurrence, whatever a retry or a second worker does."""
    assert may_process(EventStatus.APPROVED, _START, 60, True, _START - timedelta(minutes=1)) is (
        False
    )


@pytest.mark.story("SCRUM-85")
def test_a_missed_occurrence_is_still_processed_while_the_event_is_upcoming() -> None:
    """AC7: a tick that never ran catches up, rather than being lost."""
    long_after_due = _START - timedelta(minutes=1)

    assert may_process(EventStatus.APPROVED, _START, 1440, False, long_after_due) is True


@pytest.mark.story("SCRUM-85")
def test_nothing_is_sent_once_the_event_has_started() -> None:
    """AC7: reminding someone to arrange an event that is already under way is noise."""
    assert may_process(EventStatus.APPROVED, _START, 60, False, _START) is False
    assert may_process(EventStatus.APPROVED, _START, 60, False, _START + timedelta(days=1)) is (
        False
    )


@pytest.mark.story("SCRUM-85")
@pytest.mark.parametrize(
    "status",
    [
        EventStatus.CANCELLED,
        EventStatus.COMPLETED,
        EventStatus.DRAFT,
        EventStatus.SUBMITTED,
        EventStatus.REJECTED,
        EventStatus.CONFIRMED,
    ],
)
def test_no_reminder_outside_the_arranging_phase(status: EventStatus) -> None:
    """AC7 names Cancelled and Completed; the rest have no arrangements to chase.

    Confirmed is here because SCRUM-80 refuses to confirm until every arrangement and
    the safety approval are in order, so a reminder could only ask for nothing.
    """
    assert may_process(status, _START, 60, False, _START - timedelta(minutes=1)) is False


@pytest.mark.story("SCRUM-85")
def test_an_event_with_no_start_time_has_no_occurrences() -> None:
    assert may_process(EventStatus.APPROVED, None, 60, False, _START) is False


@pytest.mark.story("SCRUM-85")
def test_a_reminder_is_created_only_when_work_is_outstanding() -> None:
    """AC5: "if no work remains, create none"."""
    assert outcome_of(True) is ReminderOutcome.NOTIFIED
    assert outcome_of(False) is ReminderOutcome.NOTHING_OUTSTANDING


@pytest.mark.story("SCRUM-85")
def test_a_kept_lead_time_keeps_its_row_across_a_schedule_change() -> None:
    """AC6: rebuilding the schedule would forget what had already been sent."""
    assert retained([60, 1440], [60, 120]) == {60}
    assert retained([], [60]) == set()
    assert retained([60], []) == set()


@pytest.mark.story("SCRUM-85")
def test_a_validated_schedule_narrows_to_whole_minutes() -> None:
    """The same two conditions `lead_time_problems` applies decide what survives here,
    so a caller cannot cast a value the validator would have refused."""
    assert whole_minutes([60, 1440]) == [60, 1440]
    assert whole_minutes([60, 90.5, True, 0, -5]) == [60]
