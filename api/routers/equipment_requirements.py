"""The assigned Coordinator maintains an event's equipment requirements (SCRUM-43)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, get_current_user, require_event_access
from domain.equipment_requirement import RequirementFields
from models.event_request import EventRequest
from schemas.equipment_requirements import (
    RequirementChangeRead,
    RequirementCreate,
    RequirementRead,
    RequirementUpdate,
)
from schemas.event_requests import FieldProblemRead
from services import equipment_requirements as service

router = APIRouter(prefix="/event-requests", tags=["equipment-requirements"])

# AC10: the currently assigned coordinator, while the event is being planned. After a
# reassignment the rights move with the assignment, because this reads the event's
# coordinator_id each time rather than remembering who it was.
MaintainableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.MAINTAIN_EQUIPMENT))
]
# AC4 of SCRUM-44 and AC1 here: anyone who may see the event may read what it needs.
ViewableEvent = Annotated[EventRequest, Depends(require_event_access(EventAccess.VIEW))]
AnyUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


def _validation_error(exc: service.InvalidRequirementError) -> HTTPException:
    problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
    # A literal 422, as elsewhere in this package: Starlette renamed its constant between
    # the versions we allow.
    return HTTPException(422, [p.model_dump() for p in problems])


@router.get("/{request_id}/equipment-requirements", response_model=list[RequirementRead])
def list_requirements(event: ViewableEvent, db: Db) -> list[RequirementRead]:
    """AC1: what this event needs, as records rather than a sentence."""
    return [RequirementRead.model_validate(row) for row in service.list_for_event(db, event)]


@router.get(
    "/{request_id}/equipment-requirements/history", response_model=list[RequirementChangeRead]
)
def requirement_history(event: ViewableEvent, db: Db) -> list[RequirementChangeRead]:
    """AC7 and AC8: every add, change and removal, including requirements since removed."""
    return [
        RequirementChangeRead.model_validate(row) for row in service.history_for_event(db, event)
    ]


@router.post(
    "/{request_id}/equipment-requirements",
    response_model=RequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def add_requirement(
    event: MaintainableEvent, body: RequirementCreate, user: AnyUser, db: Db
) -> RequirementRead:
    """AC2 and AC3: add a requirement; 422 names the fields to fix."""
    try:
        added = service.add(
            db, event, RequirementFields(**body.model_dump()), _user_id(user), datetime.now(UTC)
        )
    except service.InvalidRequirementError as exc:
        raise _validation_error(exc) from exc
    return RequirementRead.model_validate(added)


@router.patch(
    "/{request_id}/equipment-requirements/{requirement_id}", response_model=RequirementRead
)
def update_requirement(
    event: MaintainableEvent,
    requirement_id: uuid.UUID,
    body: RequirementUpdate,
    user: AnyUser,
    db: Db,
) -> RequirementRead:
    """AC2 and AC5: change a requirement, which sends it back for review."""
    existing = service.list_for_event(db, event)
    current = next((row for row in existing if row.id == requirement_id), None)
    fields = RequirementFields(
        equipment_type=current.equipment_type if current is not None else None,
        quantity=body.quantity,
        technical_requirements=body.technical_requirements,
    )
    try:
        changed = service.update(
            db, event, requirement_id, fields, _user_id(user), datetime.now(UTC)
        )
    except service.RequirementNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment requirement not found") from exc
    except service.InvalidRequirementError as exc:
        raise _validation_error(exc) from exc
    return RequirementRead.model_validate(changed)


@router.delete(
    "/{request_id}/equipment-requirements/{requirement_id}", response_model=RequirementRead
)
def remove_requirement(
    event: MaintainableEvent, requirement_id: uuid.UUID, user: AnyUser, db: Db
) -> RequirementRead:
    """AC7: take it out of the live set; the row and its history stay."""
    try:
        removed = service.remove(db, event, requirement_id, _user_id(user), datetime.now(UTC))
    except service.RequirementNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment requirement not found") from exc
    return RequirementRead.model_validate(removed)
