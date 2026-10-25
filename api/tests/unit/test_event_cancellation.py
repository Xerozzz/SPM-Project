"""SCRUM-115: the pure rules for cancelling a whole event."""

import uuid

import pytest

from domain import event_status
from domain.event_cancellation import (
    TEXT_MAX_LENGTH,
    CancellationRefusal,
    cancellation_refusal,
    may_read_cancellation,
    text_problems,
)
from domain.event_status import EventAction, EventStatus, InvalidTransitionError
from domain.lifecycle_notifications import cancellation_staff
from domain.roles import Role


@pytest.mark.story("SCRUM-115")
@pytest.mark.parametrize(
    "status", [EventStatus.SUBMITTED, EventStatus.APPROVED, EventStatus.CONFIRMED]
)
def test_an_active_event_may_be_cancelled(status: EventStatus) -> None:
    assert cancellation_refusal(status) is None
    assert event_status.cancel(status) is EventStatus.CANCELLED
    assert EventAction.CANCEL in event_status.allowed_actions(status)


@pytest.mark.story("SCRUM-115")
@pytest.mark.parametrize(
    ("status", "refusal"),
    [
        (EventStatus.CANCELLED, CancellationRefusal.ALREADY_CANCELLED),
        (EventStatus.COMPLETED, CancellationRefusal.COMPLETED),
        (EventStatus.DRAFT, CancellationRefusal.NOT_ACTIVE),
        (EventStatus.REJECTED, CancellationRefusal.NOT_ACTIVE),
    ],
)
def test_other_events_are_refused_and_say_why(
    status: EventStatus, refusal: CancellationRefusal
) -> None:
    assert cancellation_refusal(status) is refusal
    with pytest.raises(InvalidTransitionError):
        event_status.cancel(status)


@pytest.mark.story("SCRUM-115")
def test_cancelled_is_terminal_in_the_status_machine() -> None:
    assert event_status.allowed_actions(EventStatus.CANCELLED) == frozenset()
    for target in EventStatus:
        with pytest.raises(InvalidTransitionError):
            event_status.transition(EventStatus.CANCELLED, target)
    with pytest.raises(InvalidTransitionError):
        event_status.replan(EventStatus.CANCELLED)
    with pytest.raises(InvalidTransitionError):
        event_status.confirm(EventStatus.CANCELLED)
    assert not event_status.is_active_status(EventStatus.CANCELLED)


@pytest.mark.story("SCRUM-115")
def test_a_reason_is_required_and_bounded() -> None:
    assert text_problems("reason", "Venue flooded") == []
    assert [p.reason for p in text_problems("reason", None)] == ["is required"]
    assert [p.field for p in text_problems("note", "   ")] == ["note"]
    assert text_problems("reason", "x" * TEXT_MAX_LENGTH) == []
    too_long = text_problems("reason", "x" * (TEXT_MAX_LENGTH + 1))
    assert [p.reason for p in too_long] == [f"must be at most {TEXT_MAX_LENGTH} characters"]
    # Surrounding spaces are trimmed before the length is checked.
    assert text_problems("reason", " " + "x" * TEXT_MAX_LENGTH + " ") == []


@pytest.mark.story("SCRUM-115")
def test_who_may_read_the_cancellation_requests() -> None:
    assert may_read_cancellation(is_owner=True, is_assigned=False, is_lead=False)
    assert may_read_cancellation(is_owner=False, is_assigned=True, is_lead=False)
    assert may_read_cancellation(is_owner=False, is_assigned=False, is_lead=True)
    assert not may_read_cancellation(is_owner=False, is_assigned=False, is_lead=False)


@pytest.mark.story("SCRUM-115")
def test_venue_technical_and_safety_staff_hear_of_a_cancellation() -> None:
    venue, tech, safety, other = (uuid.uuid4() for _ in range(4))
    roles = {
        venue: [Role.VENUE_STAFF.value],
        tech: [Role.TECH_SUPPORT.value],
        safety: [Role.SAFETY_OFFICER.value],
        other: [Role.COORDINATOR.value],
    }
    actors = [venue, tech, safety, other, uuid.uuid4()]
    assert cancellation_staff(actors, roles) == {venue, tech, safety}
