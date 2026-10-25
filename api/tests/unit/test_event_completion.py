"""SCRUM-86: the pure rules for completing an event."""

from datetime import UTC, datetime, timedelta

import pytest

from domain import event_status
from domain.event_completion import (
    NOTES_MAX_LENGTH,
    CompletionRefusal,
    clean_notes,
    closure_problems,
    completion_refusal,
    may_read_closure,
)
from domain.event_status import EventAction, EventStatus, InvalidTransitionError
from domain.validation import FieldProblem

END = datetime(2030, 3, 4, 12, tzinfo=UTC)


@pytest.mark.story("SCRUM-86")
def test_a_confirmed_event_may_be_completed_at_or_after_its_end() -> None:
    assert completion_refusal(EventStatus.CONFIRMED, END, END) is None
    assert completion_refusal(EventStatus.CONFIRMED, END, END + timedelta(days=1)) is None


@pytest.mark.story("SCRUM-86")
def test_before_the_end_or_without_one_is_refused() -> None:
    early = END - timedelta(minutes=1)
    assert completion_refusal(EventStatus.CONFIRMED, END, early) is CompletionRefusal.NOT_ENDED
    assert completion_refusal(EventStatus.CONFIRMED, None, END) is CompletionRefusal.NOT_ENDED


@pytest.mark.story("SCRUM-86")
@pytest.mark.parametrize(
    "status",
    [EventStatus.DRAFT, EventStatus.SUBMITTED, EventStatus.APPROVED, EventStatus.REJECTED],
)
def test_only_a_confirmed_event_may_be_completed(status: EventStatus) -> None:
    assert completion_refusal(status, END, END) is CompletionRefusal.NOT_CONFIRMED


@pytest.mark.story("SCRUM-86")
def test_a_completed_event_says_so() -> None:
    assert completion_refusal(EventStatus.COMPLETED, END, END) is (
        CompletionRefusal.ALREADY_COMPLETED
    )


@pytest.mark.story("SCRUM-86")
def test_completed_is_terminal_in_the_status_machine() -> None:
    assert event_status.complete(EventStatus.CONFIRMED) is EventStatus.COMPLETED
    assert event_status.allowed_actions(EventStatus.COMPLETED) == frozenset()
    assert EventAction.COMPLETE in event_status.allowed_actions(EventStatus.CONFIRMED)
    assert not event_status.is_active_status(EventStatus.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        event_status.complete(EventStatus.APPROVED)
    with pytest.raises(InvalidTransitionError):
        event_status.confirm(EventStatus.COMPLETED)


@pytest.mark.story("SCRUM-86")
def test_attendance_and_notes_are_checked() -> None:
    assert closure_problems(None, None) == []
    assert closure_problems(0, "x" * NOTES_MAX_LENGTH) == []
    assert closure_problems(-1, "x" * (NOTES_MAX_LENGTH + 1)) == [
        FieldProblem("actual_attendance", "must be zero or more"),
        FieldProblem("notes", f"must be at most {NOTES_MAX_LENGTH} characters"),
    ]


@pytest.mark.story("SCRUM-86")
def test_blank_notes_are_no_notes() -> None:
    assert clean_notes(None) is None
    assert clean_notes("   ") is None
    assert clean_notes(" Ran late ") == "Ran late"


@pytest.mark.story("SCRUM-86")
def test_who_may_read_the_closure_record() -> None:
    nobody = {"is_owner": False, "is_assigned": False, "is_lead": False}
    assert not may_read_closure(**nobody, is_participating_staff=False)
    assert may_read_closure(**nobody, is_participating_staff=True)
    assert may_read_closure(**{**nobody, "is_owner": True}, is_participating_staff=False)
    assert may_read_closure(**{**nobody, "is_assigned": True}, is_participating_staff=False)
    assert may_read_closure(**{**nobody, "is_lead": True}, is_participating_staff=False)
