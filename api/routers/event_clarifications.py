"""HTTP endpoints for event-review clarification messages (SCRUM-30)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, get_current_user, require_event_access, require_role
from domain.roles import Role
from models.event_request import EventRequest
from schemas.event_clarifications import EventClarificationCreate, EventClarificationRead
from schemas.event_requests import EventRequestRead
from services import event_clarifications as clarification_service
from services import event_requests as event_request_service

router = APIRouter(prefix="/event-requests", tags=["event-clarifications"])

AuthenticatedUser = Annotated[dict[str, object], Depends(get_current_user)]
Coordinator = Annotated[dict[str, object], Depends(require_role(Role.COORDINATOR))]
ViewableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.VIEW))
]
ClarifiableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.REQUEST_CLARIFICATION))
]
RespondableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.RESPOND_TO_CLARIFICATION))
]
Db = Annotated[Session, Depends(get_db)]


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


@router.get("/reviewable", response_model=list[EventRequestRead])
def list_reviewable_events(_user: Coordinator, db: Db) -> list[EventRequestRead]:
    """Return submitted requests available for coordinator review."""
    rows = event_request_service.list_for_review(db)
    return [EventRequestRead.model_validate(row) for row in rows]


@router.get("/{request_id}/clarifications", response_model=list[EventClarificationRead])
def list_clarifications(event: ViewableEvent, db: Db) -> list[EventClarificationRead]:
    """Return clarification requests and responses visible to this participant."""
    rows = clarification_service.list_for_event(db, event.id)
    return [EventClarificationRead.model_validate(row) for row in rows]


@router.post(
    "/{request_id}/clarifications",
    response_model=EventClarificationRead,
    status_code=status.HTTP_201_CREATED,
)
def request_clarification(
    event: ClarifiableEvent,
    body: EventClarificationCreate,
    user: AuthenticatedUser,
    db: Db,
) -> EventClarificationRead:
    """Record a coordinator's clarification request without changing event status."""
    row = clarification_service.create_message(
        db, event.id, _user_id(user), body.message, datetime.now(UTC)
    )
    return EventClarificationRead.model_validate(row)


@router.post(
    "/{request_id}/clarifications/responses",
    response_model=EventClarificationRead,
    status_code=status.HTTP_201_CREATED,
)
def respond_to_clarification(
    event: RespondableEvent,
    body: EventClarificationCreate,
    user: AuthenticatedUser,
    db: Db,
) -> EventClarificationRead:
    """Record the creating organiser's response without unlocking the submitted event."""
    row = clarification_service.create_message(
        db, event.id, _user_id(user), body.message, datetime.now(UTC)
    )
    return EventClarificationRead.model_validate(row)
