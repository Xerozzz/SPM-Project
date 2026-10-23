"""Return a Confirmed event to planning (SCRUM-130, ADR-0052).

One operation shared by an approved change request (SCRUM-47) and a venue closure
(SCRUM-132), so both reopen an event the same way.

It stages and never commits. The caller already holds the event's row lock and commits
once, so the return to planning lands or rolls back together with the decision or
closure that caused it.
"""

from datetime import datetime

from core.database import Session
from domain import event_status
from domain.event_replanning import ReplanCause, approval_to_invalidate
from domain.safety_review import SafetyDecision
from models.event_request import EventRequest
from repositories import safety_reviews as safety_repo


def return_to_planning(db: Session, event: EventRequest, cause: ReplanCause, now: datetime) -> None:
    """Move the event back to Approved and invalidate its current safety approval."""
    event.status = event_status.replan(event.status)
    history = safety_repo.list_for_event(db, event.id)
    if not history:
        return
    latest = history[-1]
    if approval_to_invalidate(SafetyDecision(latest.decision), latest.invalidated_at is not None):
        latest.invalidated_at = now
        latest.invalidation_cause = cause.value
