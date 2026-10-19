"""The assigned Coordinator maintains an event's equipment requirements (SCRUM-43),
Technical Support Staff review them (SCRUM-44), both can check availability (SCRUM-52),
and Technical Support Staff reserve against them (SCRUM-53)."""

import uuid
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, get_current_user, require_event_access, require_role
from domain.equipment_requirement import RequirementFields
from domain.equipment_reservation import ReservationRefusal
from domain.roles import Role
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from schemas.equipment_requirements import (
    RequirementAvailabilityRead,
    RequirementChangeRead,
    RequirementCreate,
    RequirementForReview,
    RequirementRead,
    RequirementRecordRead,
    RequirementReviewUpdate,
    RequirementUpdate,
    ReservationCreate,
    ReservationRead,
)
from schemas.event_requests import FieldProblemRead
from services import equipment as equipment_service
from services import equipment_requirements as service
from services import equipment_reservations as reservation_service

router = APIRouter(prefix="/event-requests", tags=["equipment-requirements"])
# SCRUM-44 works across events rather than inside one, so it has its own prefix.
review_router = APIRouter(prefix="/equipment-requirements", tags=["equipment-requirements"])

# AC10: the currently assigned coordinator, while the event is being planned. After a
# reassignment the rights move with the assignment, because this reads the event's
# coordinator_id each time rather than remembering who it was.
MaintainableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.MAINTAIN_EQUIPMENT))
]
# Reading follows ordinary event visibility, so the organiser sees what is being
# arranged for them. Technical Support Staff are not included; SCRUM-44 gives them
# the review routes at the end of this module instead.
ViewableEvent = Annotated[EventRequest, Depends(require_event_access(EventAccess.VIEW))]
CheckableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.CHECK_EQUIPMENT_AVAILABILITY))
]
AnyUser = Annotated[dict[str, object], Depends(get_current_user)]
TechSupport = Annotated[dict[str, object], Depends(require_role(Role.TECH_SUPPORT))]
Db = Annotated[Session, Depends(get_db)]

_AVAILABILITY_FIELDS = {"id", "equipment_type", "quantity", "technical_requirements"}

# SCRUM-53: asking for more than the requirement needs is a bad request (422); asking for
# more than exists, or finding nothing left to take, conflicts with what is held (409).
_REFUSAL_STATUS = {
    ReservationRefusal.ABOVE_OUTSTANDING: 422,
    ReservationRefusal.ABOVE_FREE: status.HTTP_409_CONFLICT,
    ReservationRefusal.NOTHING_OUTSTANDING: status.HTTP_409_CONFLICT,
    ReservationRefusal.NOTHING_FREE: status.HTTP_409_CONFLICT,
}


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


def _validation_error(exc: service.InvalidRequirementError) -> HTTPException:
    problems = [FieldProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
    # A literal 422, as elsewhere in this package: Starlette renamed its constant between
    # the versions we allow.
    return HTTPException(422, [p.model_dump() for p in problems])


def _reads(db: Session, rows: Sequence[EventEquipmentRequirement]) -> list[RequirementRead]:
    """SCRUM-53 AC6: each requirement with what is reserved against it."""
    return [
        RequirementRead(**RequirementRecordRead.model_validate(row).model_dump(), **asdict(held))
        for row, held in zip(rows, service.reservation_summaries(db, rows), strict=True)
    ]


@router.get("/{request_id}/equipment-requirements", response_model=list[RequirementRead])
def list_requirements(event: ViewableEvent, db: Db) -> list[RequirementRead]:
    """AC1: what this event needs, as records rather than a sentence."""
    return _reads(db, service.list_for_event(db, event))


@router.get("/{request_id}/equipment-requirements/catalogue-types", response_model=list[str])
def list_catalogue_types(event: MaintainableEvent, db: Db) -> list[str]:
    """AC3: the active types this event's Coordinator may choose from.

    The organiser has `/event-requests/equipment-types` for the same list, but that route
    is theirs: a Coordinator asking it is refused, which left AC3 with no way to offer the
    catalogue on the screen they actually use.

    Guarded by the same access as maintaining a requirement rather than by a role, so the
    vocabulary is readable exactly when choosing from it is allowed (AC10), and a
    reassignment moves it with everything else.
    """
    del event
    return equipment_service.list_distinct_types(db)


@router.get(
    "/{request_id}/equipment-requirements/history", response_model=list[RequirementChangeRead]
)
def requirement_history(event: ViewableEvent, db: Db) -> list[RequirementChangeRead]:
    """AC7 and AC8: every add, change and removal, including requirements since removed."""
    return [
        RequirementChangeRead.model_validate(row) for row in service.history_for_event(db, event)
    ]


@router.get(
    "/{request_id}/equipment-availability", response_model=list[RequirementAvailabilityRead]
)
def equipment_availability(event: CheckableEvent, db: Db) -> list[RequirementAvailabilityRead]:
    """SCRUM-52: whether each requirement can be met; 409 outside planning. Reserves nothing."""
    try:
        checked = service.check_availability(db, event)
    except service.ReviewNotAllowedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Event is not in planning") from exc
    return [
        RequirementAvailabilityRead(
            **RequirementRecordRead.model_validate(row).model_dump(include=_AVAILABILITY_FIELDS),
            event_start_at=event.start_at,
            event_end_at=event.end_at,
            **asdict(availability),
        )
        for row, availability in checked
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
    return _reads(db, [added])[0]


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
    """AC2 and AC5: change a requirement, which sends it back for review.

    `exclude_unset` is what makes this a real PATCH: a field the caller left out keeps its
    value rather than being erased. Sending `technical_requirements: null` still clears it,
    because that is an answer rather than a silence.
    """
    try:
        changed = service.update(
            db,
            event,
            requirement_id,
            body.model_dump(exclude_unset=True),
            _user_id(user),
            datetime.now(UTC),
        )
    except service.RequirementNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment requirement not found") from exc
    except service.InvalidRequirementError as exc:
        raise _validation_error(exc) from exc
    return _reads(db, [changed])[0]


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
    return _reads(db, [removed])[0]


@review_router.get("/review", response_model=list[RequirementForReview])
def list_for_review(_: TechSupport, db: Db) -> list[RequirementForReview]:
    """SCRUM-44 AC1: every live requirement of an event in planning, with its timing."""
    pairs = service.list_for_review(db)
    reads = _reads(db, [row for row, _ in pairs])
    return [
        RequirementForReview(
            **read.model_dump(),
            event_name=event.name,
            event_start_at=event.start_at,
            event_end_at=event.end_at,
        )
        for read, (_, event) in zip(reads, pairs, strict=True)
    ]


@review_router.patch("/{requirement_id}/review", response_model=RequirementRead)
def review_requirement(
    requirement_id: uuid.UUID, body: RequirementReviewUpdate, _: TechSupport, db: Db
) -> RequirementRead:
    """SCRUM-44 AC2: record whether it can be fulfilled; 404 if removed, 409 outside planning."""
    try:
        reviewed = service.review(db, requirement_id, body.review_status, datetime.now(UTC))
    except service.RequirementNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment requirement not found") from exc
    except service.ReviewNotAllowedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Event is not in planning") from exc
    return _reads(db, [reviewed])[0]


@router.post(
    "/{request_id}/equipment-requirements/{requirement_id}/reserve",
    response_model=ReservationRead,
    status_code=status.HTTP_201_CREATED,
)
def reserve_equipment(
    request_id: uuid.UUID,
    requirement_id: uuid.UUID,
    user: TechSupport,
    db: Db,
    body: ReservationCreate | None = None,
) -> ReservationRead:
    """SCRUM-53: reserve what is needed and free; 404 missing, 409 outside planning or short."""
    asked = body.quantity if body else None
    try:
        outcome = reservation_service.reserve(
            db, request_id, requirement_id, asked, _user_id(user), datetime.now(UTC)
        )
    except service.RequirementNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment requirement not found") from exc
    except service.ReviewNotAllowedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Event is not in planning") from exc
    except reservation_service.EventWindowMissingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Event has no start or end time") from exc
    except reservation_service.ReservationRefusedError as exc:
        raise HTTPException(_REFUSAL_STATUS[exc.refusal], exc.refusal.value) from exc
    return ReservationRead(**asdict(outcome))
