"""The event request status machine — the one place a status may change (AGENTS.md §3).

Nothing else in the codebase assigns `event_request.status`. A service that needs to move a
request asks this module for the new status and stores whatever comes back; if the move is
not allowed, it gets an exception instead. That keeps every legal path in one table that a
reviewer, a tester, or an instructor can read in ten seconds.

Stories add transitions here as they land, each with its own tests:

    SCRUM-46  draft -> submitted
    SCRUM-31  submitted -> approved | rejected        (review and decide)
    SCRUM-30  submitted -> clarification_requested    (request clarification)
    SCRUM-35  allowed_actions: what a status permits

SCRUM-34 pre-declares the `CONFIRMED` value below, ahead of any story landing the
transition into it: coordinator assignment needs to ask "does this coordinator already
have a confirmed event that date", and that question has to name a real status. The
transition into CONFIRMED itself — and who is allowed to make it — stays a later
story's to add.
"""

from enum import StrEnum


class EventStatus(StrEnum):
    """Every status an event request can be in. Stored as its lowercase value."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"


class EventAction(StrEnum):
    """Something a user may do to an event request. Sent to the UI as these values."""

    EDIT = "edit"
    SUBMIT = "submit"


class InvalidTransitionError(Exception):
    """The requested status change is not in the transition table."""

    def __init__(self, current: EventStatus, target: EventStatus) -> None:
        super().__init__(f"cannot move an event request from {current} to {target}")
        self.current = current
        self.target = target


class EventRequestLockedError(Exception):
    """The request has left DRAFT, so its content may no longer be edited directly."""

    def __init__(self, status: EventStatus) -> None:
        super().__init__(f"an event request in status {status} cannot be edited")
        self.status = status


# The whole state machine, as data: each legal move and the action that performs it. A
# transition that is not listed here does not exist, and an entry added here is offered by
# allowed_actions without anything else changing.
_ALLOWED_TRANSITIONS: dict[tuple[EventStatus, EventStatus], EventAction] = {
    (EventStatus.DRAFT, EventStatus.SUBMITTED): EventAction.SUBMIT,
}


class EventRequestNotSubmittedError(Exception):
    """The request is still a draft, so downstream workflows must ignore it."""

    def __init__(self, status: EventStatus) -> None:
        super().__init__(f"an event request in status {status} is not submitted")
        self.status = status


def transition(current: EventStatus, target: EventStatus) -> EventStatus:
    """Return `target` if moving there from `current` is allowed, else raise."""
    if (current, target) not in _ALLOWED_TRANSITIONS:
        raise InvalidTransitionError(current, target)
    return target


def submit(current: EventStatus) -> EventStatus:
    """SCRUM-46: an organiser submits a draft for coordinator review."""
    return transition(current, EventStatus.SUBMITTED)


def is_editable(status: EventStatus) -> bool:
    """Only a draft may be edited directly. After submission, changes go through the
    assigned coordinator (Event Change Management, a later epic)."""
    return status is EventStatus.DRAFT


def ensure_editable(status: EventStatus) -> None:
    """Raise unless the request may be edited directly."""
    if not is_editable(status):
        raise EventRequestLockedError(status)


def allowed_actions(status: EventStatus) -> frozenset[EventAction]:
    """SCRUM-35: what may be done to a request in `status`, from the rules above."""
    actions = {action for (source, _), action in _ALLOWED_TRANSITIONS.items() if source == status}
    if is_editable(status):
        actions.add(EventAction.EDIT)
    return frozenset(actions)


def is_downstream_available(status: EventStatus) -> bool:
    """Only submitted requests may enter assignment, review, booking, or registration."""
    return status is EventStatus.SUBMITTED


def ensure_downstream_available(status: EventStatus) -> None:
    """Raise unless downstream workflows may act on this request."""
    if not is_downstream_available(status):
        raise EventRequestNotSubmittedError(status)
