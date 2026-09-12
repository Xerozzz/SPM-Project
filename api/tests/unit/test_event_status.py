"""SCRUM-46 (F6): the only legal way to change an event request's status."""

import pytest

from domain.event_status import (
    EventRequestLockedError,
    EventStatus,
    InvalidTransitionError,
    ensure_editable,
    is_editable,
    submit,
    transition,
)


@pytest.mark.story("SCRUM-46")
def test_a_draft_can_be_submitted() -> None:
    assert submit(EventStatus.DRAFT) is EventStatus.SUBMITTED


@pytest.mark.story("SCRUM-46")
def test_a_submitted_request_cannot_be_submitted_again() -> None:
    with pytest.raises(InvalidTransitionError) as exc:
        submit(EventStatus.SUBMITTED)

    assert exc.value.current is EventStatus.SUBMITTED
    assert exc.value.target is EventStatus.SUBMITTED


@pytest.mark.story("SCRUM-46")
def test_unlisted_transitions_are_rejected() -> None:
    # SUBMITTED -> DRAFT is not in the table; nothing "un-submits" a request.
    with pytest.raises(InvalidTransitionError):
        transition(EventStatus.SUBMITTED, EventStatus.DRAFT)


@pytest.mark.story("SCRUM-46")
def test_only_a_draft_is_editable() -> None:
    assert is_editable(EventStatus.DRAFT)
    assert not is_editable(EventStatus.SUBMITTED)


@pytest.mark.story("SCRUM-46")
def test_ensure_editable_passes_for_a_draft_and_raises_after_submission() -> None:
    ensure_editable(EventStatus.DRAFT)

    with pytest.raises(EventRequestLockedError) as exc:
        ensure_editable(EventStatus.SUBMITTED)

    assert exc.value.status is EventStatus.SUBMITTED


@pytest.mark.story("SCRUM-46")
def test_status_values_are_lowercase_strings_for_storage() -> None:
    assert EventStatus.SUBMITTED.value == "submitted"
    assert EventStatus("draft") is EventStatus.DRAFT
