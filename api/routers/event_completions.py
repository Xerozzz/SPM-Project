"""Completing an event and its closure record (SCRUM-86).

Its own module, like SCRUM-80's confirmation: the paths sit under `/event-requests`
because that is what is being completed, but nothing is shared with the other routes.
Who may act is the access rule (`COMPLETE_EVENT`, `READ_EVENT_CLOSURE`), not a check here.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import (
    EventAccess,
    get_current_user,
    require_event_access,
    require_role,
)
from domain.event_completion import CompletionRefusal
from domain.roles import Role
from models.event_request import EventRequest
from schemas.event_completions import ClosureInput, ClosureNoteRead, ClosureRead
from schemas.event_requests import EventRequestRead, FieldProblemRead
from services import event_completions as service

router = APIRouter(prefix="/event-requests", tags=["event-completion"])

CompletableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.COMPLETE_EVENT))
]
ClosureReader = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.READ_EVENT_CLOSURE))
]
CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]
Coordinator = Annotated[dict[str, object], Depends(require_role(Role.COORDINATOR))]
Db = Annotated[Session, Depends(get_db)]

# What the Coordinator is told when the event cannot be completed now.
_REFUSALS = {
    CompletionRefusal.ALREADY_COMPLETED: "This event is already completed",
    CompletionRefusal.NOT_CONFIRMED: "Only a confirmed event can be completed",
    CompletionRefusal.NOT_ENDED: "This event has not ended yet",
}


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


def _invalid(exc: service.InvalidClosureError) -> HTTPException:
    problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
    return HTTPException(422, [p.model_dump() for p in problems])


@router.get("/assigned-completed", response_model=list[EventRequestRead])
def list_completed(user: Coordinator, db: Db) -> list[EventRequestRead]:
    """Completed events assigned to this Coordinator, so the record can be corrected."""
    rows = service.completed_for_coordinator(db, _user_id(user))
    return [EventRequestRead.model_validate(row) for row in rows]


@router.post("/{request_id}/complete", response_model=ClosureRead)
def complete(event: CompletableEvent, body: ClosureInput, user: CurrentUser, db: Db) -> ClosureRead:
    """AC1 to AC3, AC6: complete the event and record its first closure version."""
    try:
        done = service.complete(
            db, event.id, _user_id(user), body.actual_attendance, body.notes, datetime.now(UTC)
        )
    except service.NotCompletableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, _REFUSALS[exc.refusal]) from exc
    except service.InvalidClosureError as exc:
        raise _invalid(exc) from exc
    return ClosureRead.of(done, service.history_of(db, done))


@router.post("/{request_id}/closure-notes", response_model=ClosureNoteRead, status_code=201)
def correct(
    event: CompletableEvent, body: ClosureInput, user: CurrentUser, db: Db
) -> ClosureNoteRead:
    """AC5: a correction adds a version. Earlier versions stay as they were."""
    try:
        note = service.correct(
            db, event.id, _user_id(user), body.actual_attendance, body.notes, datetime.now(UTC)
        )
    except service.NotCompletedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only a completed event has closure notes to correct"
        ) from exc
    except service.InvalidClosureError as exc:
        raise _invalid(exc) from exc
    return ClosureNoteRead.model_validate(note)


@router.get("/{request_id}/closure", response_model=ClosureRead)
def read_closure(event: ClosureReader, db: Db) -> ClosureRead:
    """AC4: the completion and the closure record, for the people allowed to see it."""
    return ClosureRead.of(event, service.history_of(db, event))
