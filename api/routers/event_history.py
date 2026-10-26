"""An event's history (SCRUM-88). HTTP only: authorise via the shared dependency,
delegate to the service, serialise."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, clarification_visibility, require_event_access
from models.event_request import EventRequest
from schemas.event_history import EventHistoryEntryRead
from services import event_history as service

router = APIRouter(prefix="/event-requests", tags=["event-history"])

HistoryReadableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.READ_EVENT_HISTORY))
]
ClarificationVisibility = Annotated[
    Callable[[EventRequest], bool], Depends(clarification_visibility)
]
Db = Annotated[Session, Depends(get_db)]


@router.get("/{request_id}/history", response_model=list[EventHistoryEntryRead])
def read_history(
    event: HistoryReadableEvent, may_read_clarifications: ClarificationVisibility, db: Db
) -> list[EventHistoryEntryRead]:
    """AC1-AC3: the event's recorded actions, oldest first, for the owner, the current
    assigned Coordinator or any Lead (ADR-0062). Internal notes only for the assignee."""
    entries = service.history_of(db, event, may_read_clarifications(event))
    return [EventHistoryEntryRead.from_entry(entry) for entry in entries]
