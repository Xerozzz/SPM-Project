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
    SCRUM-47  confirmed -> approved                   (an approved change reopens planning)
    SCRUM-86  confirmed -> completed                  (the event has run, terminal)
    SCRUM-115 submitted | approved | confirmed -> cancelled  (terminal)

SCRUM-34 pre-declared the `CONFIRMED` value ahead of any story landing the transition
into it: coordinator assignment needs to ask "does this coordinator already have a
confirmed event that date", and that question has to name a real status. SCRUM-80 adds
the transition itself, approved -> confirmed, performed by the assigned Coordinator once
`domain.event_confirmation` says the arrangements and the safety review allow it.
"""

from enum import StrEnum


class EventStatus(StrEnum):
    """Every status an event request can be in. Stored as its lowercase value."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    APPROVED = "approved"
    REJECTED = "rejected"
    # SCRUM-86: the event has run and its Coordinator closed it. Terminal, nothing leaves it.
    COMPLETED = "completed"
    # SCRUM-115: the assigned Coordinator cancelled the event. Terminal, nothing leaves it.
    CANCELLED = "cancelled"


class EventAction(StrEnum):
    """Something a user may do to an event request. Sent to the UI as these values."""

    EDIT = "edit"
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    REPLAN = "replan"
    # SCRUM-80: the assigned Coordinator commits the event once every arrangement and
    # the safety review are in order.
    CONFIRM = "confirm"
    # SCRUM-86: the assigned Coordinator closes an event that has run.
    COMPLETE = "complete"
    # SCRUM-115: the assigned Coordinator cancels an active event.
    CANCEL = "cancel"


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
    (EventStatus.SUBMITTED, EventStatus.APPROVED): EventAction.APPROVE,
    (EventStatus.SUBMITTED, EventStatus.REJECTED): EventAction.REJECT,
    (EventStatus.REJECTED, EventStatus.SUBMITTED): EventAction.SUBMIT,
    (EventStatus.APPROVED, EventStatus.CONFIRMED): EventAction.CONFIRM,
    (EventStatus.CONFIRMED, EventStatus.APPROVED): EventAction.REPLAN,
    (EventStatus.CONFIRMED, EventStatus.COMPLETED): EventAction.COMPLETE,
    (EventStatus.SUBMITTED, EventStatus.CANCELLED): EventAction.CANCEL,
    (EventStatus.APPROVED, EventStatus.CANCELLED): EventAction.CANCEL,
    (EventStatus.CONFIRMED, EventStatus.CANCELLED): EventAction.CANCEL,
}


def transition(current: EventStatus, target: EventStatus) -> EventStatus:
    """Return `target` if moving there from `current` is allowed, else raise."""
    if (current, target) not in _ALLOWED_TRANSITIONS:
        raise InvalidTransitionError(current, target)
    return target


def submit(current: EventStatus) -> EventStatus:
    """SCRUM-46: an organiser submits a draft for coordinator review."""
    return transition(current, EventStatus.SUBMITTED)


def approve(current: EventStatus) -> EventStatus:
    """SCRUM-31: a coordinator accepts a submitted request for planning."""
    return transition(current, EventStatus.APPROVED)


def reject(current: EventStatus) -> EventStatus:
    """SCRUM-31: a coordinator returns a submitted request with a reason."""
    return transition(current, EventStatus.REJECTED)


def confirm(current: EventStatus) -> EventStatus:
    """SCRUM-80: the assigned Coordinator commits a planned event.

    Only the status move lives here. Whether the arrangements and the safety review
    allow it is `domain.event_confirmation`'s question, asked before this is called —
    the same split SCRUM-110 made between `venue_booking.approve` and the hold rules.
    """
    return transition(current, EventStatus.CONFIRMED)


def replan(current: EventStatus) -> EventStatus:
    """SCRUM-47 AC5: an approved significant change returns a Confirmed event to planning.

    Checked by action, not only by target: Submitted -> Approved is the review approval
    (SCRUM-31), which is a different decision and must not pass as a replan.
    """
    if _ALLOWED_TRANSITIONS.get((current, EventStatus.APPROVED)) is not EventAction.REPLAN:
        raise InvalidTransitionError(current, EventStatus.APPROVED)
    return EventStatus.APPROVED


def complete(current: EventStatus) -> EventStatus:
    """SCRUM-86: the assigned Coordinator closes a Confirmed event that has run.

    Only the status move lives here. Whether the event has ended is
    `domain.event_completion`'s question. Completed has no way out, so it cannot be
    reconfirmed or replanned.
    """
    return transition(current, EventStatus.COMPLETED)


def cancel(current: EventStatus) -> EventStatus:
    """SCRUM-115 AC2, AC3: the assigned Coordinator cancels a submitted, planning or
    Confirmed event.

    Only the status move lives here. Releasing the event's arrangements is
    `services.event_cancellations`'s job, in the same transaction. Cancelled has no way
    out, so nothing can reconfirm or resume it (AC7).
    """
    return transition(current, EventStatus.CANCELLED)


def is_editable(status: EventStatus) -> bool:
    """Drafts and rejected requests may be edited directly; an approved or submitted
    request remains locked."""
    return status in {EventStatus.DRAFT, EventStatus.REJECTED}


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


# SCRUM-100: which statuses count as "active" for the Lead assignment overview.
# Active means the request still needs coordinator ownership or planning attention:
# SUBMITTED (awaiting review/assignment), APPROVED (planning), CONFIRMED (committed).
# DRAFT (never submitted), REJECTED, COMPLETED and CANCELLED (terminal) are inactive.
ACTIVE_STATUSES: frozenset[EventStatus] = frozenset(
    {EventStatus.SUBMITTED, EventStatus.APPROVED, EventStatus.CONFIRMED}
)


def is_active_status(status: EventStatus) -> bool:
    """SCRUM-100: True when the request belongs in the Lead active-assignment overview."""
    return status in ACTIVE_STATUSES
