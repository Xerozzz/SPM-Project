"""HTTP endpoints for significant-change requests (SCRUM-37)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, get_current_user, require_event_access
from domain.change_decision import AlreadyDecidedError
from domain.validation import FieldProblem
from models.event_request import EventRequest
from schemas.event_change_requests import (
    ChangeDecisionCreate,
    ChangePlanRead,
    EventChangeRequestCreate,
    EventChangeRequestRead,
)
from services import event_change_requests as service
from services.event_requests import EventRequestNotFoundError, NotAuthorisedError

router = APIRouter(prefix="/event-requests", tags=["event-change-requests"])

AuthenticatedUser = Annotated[dict[str, object], Depends(get_current_user)]
ProposableEvent = Annotated[EventRequest, Depends(require_event_access(EventAccess.PROPOSE_CHANGE))]
ReadableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.READ_CHANGE_REQUESTS))
]
DecidableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.DECIDE_CHANGE_REQUEST))
]
Db = Annotated[Session, Depends(get_db)]


@router.post(
    "/{request_id}/change-requests",
    response_model=EventChangeRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def propose_change(
    event: ProposableEvent,
    body: EventChangeRequestCreate,
    user: AuthenticatedUser,
    response: Response,
    db: Db,
) -> EventChangeRequestRead:
    """AC1: record a proposal. A retried submit returns its first request with 200 (AC8)."""
    organiser_id = uuid.UUID(str(user["sub"]))
    proposal, key = body.to_proposal(), body.submission_key
    try:
        row, created = service.submit(db, event.id, organiser_id, proposal, key, datetime.now(UTC))
    except service.InvalidChangeRequestError as exc:
        raise HTTPException(422, _problems(exc.problems)) from exc
    except (EventRequestNotFoundError, NotAuthorisedError) as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden") from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return EventChangeRequestRead.model_validate(row)


@router.get("/{request_id}/change-requests", response_model=list[EventChangeRequestRead])
def list_change_requests(event: ReadableEvent, db: Db) -> list[EventChangeRequestRead]:
    """AC6: the event's change requests, for its Organiser and current Coordinator."""
    return [EventChangeRequestRead.model_validate(r) for r in service.list_for_event(db, event.id)]


@router.get("/{request_id}/change-requests/plan", response_model=ChangePlanRead)
def change_plan(event: ProposableEvent, db: Db) -> ChangePlanRead:
    """The current values and choices the Organiser's change form starts from."""
    return ChangePlanRead.build(*service.plan_for(db, event))


@router.post(
    "/{request_id}/change-requests/{change_id}/decision",
    response_model=EventChangeRequestRead,
)
def decide_change_request(
    event: DecidableEvent,
    change_id: uuid.UUID,
    body: ChangeDecisionCreate,
    user: AuthenticatedUser,
    db: Db,
) -> EventChangeRequestRead:
    """SCRUM-47: the assigned Coordinator approves or rejects a pending change request."""
    coordinator_id = uuid.UUID(str(user["sub"]))
    try:
        row = service.decide(
            db, event.id, change_id, coordinator_id, body.decision, body.note, datetime.now(UTC)
        )
    except service.InvalidChangeRequestError as exc:
        raise HTTPException(422, _problems(exc.problems)) from exc
    except service.StaleChangeRequestError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, _problems(exc.problems)) from exc
    except AlreadyDecidedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except service.ChangeRequestNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found") from exc
    except (EventRequestNotFoundError, NotAuthorisedError) as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden") from exc
    return EventChangeRequestRead.model_validate(row)


def _problems(problems: list[FieldProblem]) -> list[dict[str, str]]:
    return [{"field": p.field, "reason": p.reason} for p in problems]
