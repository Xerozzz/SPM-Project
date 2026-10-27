"""Returning a Confirmed event to planning (SCRUM-130, ADR-0052). Pure, no database.

A Confirmed event goes back to planning when its plan is no longer the one that was
confirmed: an approved change request (SCRUM-47), a venue closure (SCRUM-132), or an
arrangement the Coordinator cancelled as a venue change (SCRUM-118). The
safety approval that let it be confirmed judged the old plan, so it stops counting and
the plan has to be reviewed again before the event is reconfirmed.

The approval is marked, never deleted, so who gave it and when stay in the history.
"""

from enum import StrEnum

from domain.event_status import EventStatus
from domain.safety_review import SafetyDecision


class ReplanCause(StrEnum):
    """Why an event went back to planning, stored on the approval it invalidated."""

    CHANGE_REQUEST = "change_request"
    VENUE_CLOSURE = "venue_closure"
    # SCRUM-118: the Coordinator cancelled an arrangement as a venue change (ADR-0066).
    VENUE_CANCELLATION = "venue_cancellation"


def needs_replanning(status: EventStatus) -> bool:
    """Only a Confirmed event goes back. One already in planning is left as it is."""
    return status == EventStatus.CONFIRMED


def approval_to_invalidate(decision: SafetyDecision | None, invalidated: bool) -> bool:
    """Is the latest decision an approval that still counts?

    A rejection or a request for changes already blocks confirmation, and an approval
    already invalidated keeps its first cause and time.
    """
    return decision is SafetyDecision.APPROVE and not invalidated
