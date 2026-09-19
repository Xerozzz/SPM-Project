"""SCRUM-46 (F6): the only legal way to change an event request's status."""

import pytest

from domain.event_status import (
    _ALLOWED_TRANSITIONS,
    EventAction,
    EventRequestLockedError,
    EventStatus,
    InvalidTransitionError,
    allowed_actions,
    approve,
    ensure_editable,
    is_editable,
    reject,
    submit,
    transition,
)


@pytest.mark.story("SCRUM-46")
def test_a_draft_can_be_submitted() -> None:
    assert submit(EventStatus.DRAFT) is EventStatus.SUBMITTED


@pytest.mark.story("SCRUM-31")
def test_a_submitted_request_can_be_approved_or_rejected_then_resubmitted() -> None:
    assert approve(EventStatus.SUBMITTED) is EventStatus.APPROVED
    assert reject(EventStatus.SUBMITTED) is EventStatus.REJECTED
    assert submit(EventStatus.REJECTED) is EventStatus.SUBMITTED


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
    assert is_editable(EventStatus.REJECTED)
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


@pytest.mark.story("SCRUM-35")
def test_a_draft_may_be_edited_and_submitted() -> None:
    assert allowed_actions(EventStatus.DRAFT) == {EventAction.EDIT, EventAction.SUBMIT}


@pytest.mark.story("SCRUM-35")
def test_a_submitted_request_permits_coordinator_decisions() -> None:
    assert allowed_actions(EventStatus.SUBMITTED) == {EventAction.APPROVE, EventAction.REJECT}


@pytest.mark.story("SCRUM-35")
def test_every_transition_offers_its_action() -> None:
    # A transition added to the table whose action never reaches allowed_actions fails here,
    # so adding a move cannot silently leave the UI without its button.
    for (source, _), action in _ALLOWED_TRANSITIONS.items():
        if action is not None:
            assert action in allowed_actions(source)


@pytest.mark.story("SCRUM-35")
def test_every_action_except_edit_comes_from_a_transition() -> None:
    # EDIT is not a transition; every other action must be one, or it can never be offered.
    transition_actions = {action for action in _ALLOWED_TRANSITIONS.values() if action is not None}
    assert transition_actions == set(EventAction) - {EventAction.EDIT}


@pytest.mark.story("SCRUM-35")
def test_actions_are_lowercase_strings_for_the_api() -> None:
    assert EventAction.SUBMIT.value == "submit"
    assert EventAction.EDIT.value == "edit"
    assert EventAction.APPROVE.value == "approve"
    assert EventAction.REJECT.value == "reject"
