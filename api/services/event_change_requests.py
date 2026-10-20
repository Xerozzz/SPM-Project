"""Significant-change requests (SCRUM-37): an Organiser proposes, nothing is applied.

`submit` checks a proposal against the event's current plan with the pure rules in
`domain.event_change`, then records the request and one row per changed value. It never
writes to the event, its venue requests or its equipment lines (AC5). Deciding and
applying belong to SCRUM-47, and the Coordinator's notification to SCRUM-50, which reads
the committed request as its source action (AC8).
"""

import uuid
from datetime import datetime

from core.database import Session
from domain.event_change import (
    EVENT_FIELDS,
    Catalogue,
    ChangeItem,
    ChangeRequestStatus,
    CurrentPlan,
    PlannedSession,
    Proposal,
    Requirement,
    accepts_change_request,
    plan_change,
)
from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus
from models.event_change_request import EventChangeItem, EventChangeRequest
from models.event_request import EventRequest
from repositories import equipment as equipment_repo
from repositories import equipment_requirements as requirements_repo
from repositories import event_change_requests as repo
from repositories import event_requests as event_repo
from repositories import venue_availability
from services import venues as venues_service
from services.event_requests import EventRequestNotFoundError, NotAuthorisedError

# Venue requests that still stand. Rejected, cancelled and expired ones are history.
LIVE_BOOKINGS = frozenset({BookingStatus.PENDING, BookingStatus.TENTATIVE, BookingStatus.CONFIRMED})


class InvalidChangeRequestError(Exception):
    """AC4: the proposal cannot be recorded until these problems are fixed."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("change request is not valid")
        self.problems = problems


def submit(
    db: Session,
    event_request_id: uuid.UUID,
    organiser_id: uuid.UUID,
    proposal: Proposal,
    submission_key: uuid.UUID,
    now: datetime,
) -> tuple[EventChangeRequest, bool]:
    """Record a proposal. Returns the request and whether this call created it.

    A retry of a submit that already succeeded returns the first request unchanged (AC8).
    """
    earlier = repo.get_by_submission(db, event_request_id, submission_key)
    if earlier is not None:
        return earlier, False
    # Locked read, so the status, owner and current values checked here are the ones the
    # snapshot records; a concurrent ordinary edit waits rather than slipping in between.
    event = event_repo.get_for_update(db, event_request_id)
    if event is None:
        raise EventRequestNotFoundError
    if event.organiser_id != organiser_id or not accepts_change_request(event.status):
        raise NotAuthorisedError
    items, problems = plan_change(proposal, _current_plan(db, event), _catalogue(db), now)
    if problems:
        raise InvalidChangeRequestError(problems)
    change = EventChangeRequest(
        event_request_id=event.id,
        requested_by_id=organiser_id,
        submission_key=submission_key,
        reason=proposal.reason.strip(),
        status=ChangeRequestStatus.PENDING,
        event_updated_at=event.updated_at,
        created_at=now,
        items=[_row(position, item) for position, item in enumerate(items)],
    )
    try:
        return repo.save(db, change), True
    except repo.DuplicateSubmissionError:
        # Two copies of the same submit raced; the other one won. Return its request.
        winner = repo.get_by_submission(db, event_request_id, submission_key)
        assert winner is not None
        return winner, False


def list_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventChangeRequest]:
    """AC6: the event's change requests, newest first. Access is checked by the route."""
    return repo.list_for_event(db, event_request_id)


def plan_for(db: Session, event: EventRequest) -> tuple[CurrentPlan, Catalogue]:
    """The values a proposal starts from and the choices it may pick, for the form."""
    return _current_plan(db, event), _catalogue(db)


def _catalogue(db: Session) -> Catalogue:
    return Catalogue(
        venue_names=venues_service.list_selectable_names(db),
        equipment_types=frozenset(equipment_repo.list_distinct_active_types(db)),
    )


def _current_plan(db: Session, event: EventRequest) -> CurrentPlan:
    sessions = tuple(
        PlannedSession(b.id, b.session_label, b.start_at, b.end_at)
        for b in venue_availability.list_bookings_for_event(db, event.id)
        if b.status in LIVE_BOOKINGS
    )
    equipment = tuple(
        Requirement(r.id, r.equipment_type, r.quantity, r.technical_requirements)
        for r in requirements_repo.list_for_event(db, event.id)
    )
    values = {name: getattr(event, name) for name in EVENT_FIELDS}
    return CurrentPlan(event=values, sessions=sessions, equipment=equipment)


def _row(position: int, item: ChangeItem) -> EventChangeItem:
    return EventChangeItem(
        position=position,
        target=item.target.value,
        target_id=item.target_id,
        field=item.field,
        current_value=_json(item.current),
        proposed_value=_json(item.proposed),
    )


def _json(value: object) -> object:
    """Dates are stored as ISO 8601 text; everything else is already JSON."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value
