"""Attendee registration endpoints: HTTP/auth only."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, get_current_user, require_event_access, require_role
from domain.roles import Role
from models.event_request import EventRequest
from schemas.event_registrations import (
    AttendeeEventRead,
    RegistrationDecision,
    RegistrationDecisionRead,
    RegistrationRead,
    RegistrationReviewRead,
    RegistrationSubmit,
    WithdrawalRead,
)
from services import event_registrations as service

router = APIRouter(prefix="/attendee", tags=["attendee-registrations"])
review_router = APIRouter(prefix="/event-requests", tags=["event-registrations"])
Attendee = Annotated[dict[str, object], Depends(require_role(Role.ATTENDEE))]
ReviewableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.READ_REGISTRATIONS))
]
ManageableRegistrationEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.MANAGE_REGISTRATION))
]
CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]


def _attendee_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


@router.get("/events", response_model=list[AttendeeEventRead])
def list_events(user: Attendee, db: Db) -> list[AttendeeEventRead]:
    events = service.list_events_for_attendee(db, _attendee_id(user), datetime.now(UTC))
    return [
        AttendeeEventRead.model_validate(event).model_copy(update={"intake_open": intake_open})
        for event, intake_open in events
    ]


@router.get("/events/{event_id}", response_model=AttendeeEventRead)
def read_event(event_id: uuid.UUID, _user: Attendee, db: Db) -> AttendeeEventRead:
    try:
        event = service.event_for_registration(db, event_id, datetime.now(UTC))
    except service.EventNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Event is not open for registration"
        ) from exc
    return AttendeeEventRead.model_validate(event).model_copy(update={"intake_open": True})


@router.post(
    "/events/{event_id}/registrations",
    response_model=RegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
def submit(
    event_id: uuid.UUID, body: RegistrationSubmit, user: Attendee, db: Db
) -> RegistrationRead:
    try:
        registration = service.submit(
            db,
            event_id,
            _attendee_id(user),
            body.full_name,
            body.age,
            body.phone_number,
            body.dietary_accessibility_notes,
            datetime.now(UTC),
        )
    except service.EventNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Event is not open for registration"
        ) from exc
    except service.DuplicateRegistrationError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            RegistrationRead.of(exc.registration).model_dump(mode="json"),
        ) from exc
    except service.RegistrationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return RegistrationRead.of(registration)


@router.get("/events/{event_id}/registration", response_model=RegistrationRead)
def read_mine(event_id: uuid.UUID, user: Attendee, db: Db) -> RegistrationRead:
    registration = service.get_mine(db, event_id, _attendee_id(user))
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")
    return RegistrationRead.of(registration)


@review_router.get("/{request_id}/registrations", response_model=list[RegistrationReviewRead])
def list_registrations(event: ReviewableEvent, db: Db) -> list[RegistrationReviewRead]:
    registrations = service.list_for_event(db, event.id)
    return [RegistrationReviewRead.model_validate(row) for row in registrations]


@review_router.post(
    "/{request_id}/registrations/{registration_id}/decision",
    response_model=RegistrationDecisionRead,
)
def record_decision(
    registration_id: uuid.UUID,
    body: RegistrationDecision,
    event: ManageableRegistrationEvent,
    user: CurrentUser,
    db: Db,
) -> RegistrationDecisionRead:
    return _record_decision(db, event.id, registration_id, uuid.UUID(str(user["sub"])), body)


def _record_decision(
    db: Session,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
    actor_id: uuid.UUID,
    body: RegistrationDecision,
) -> RegistrationDecisionRead:
    try:
        registration, already_decided = service.decide(
            db,
            event_id,
            registration_id,
            actor_id,
            body.expected_status,
            body.status,
            body.note,
            datetime.now(UTC),
        )
    except service.EventNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found") from exc
    except service.RegistrationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found") from exc
    except service.StaleRegistrationDecisionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except service.RegistrationDecisionNotAllowedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return RegistrationDecisionRead.model_validate(registration).model_copy(
        update={"already_decided": already_decided}
    )


@router.post("/events/{event_id}/registration/withdraw", response_model=WithdrawalRead)
def withdraw(event_id: uuid.UUID, user: Attendee, db: Db) -> WithdrawalRead:
    try:
        registration, already_withdrawn = service.withdraw(
            db, event_id, _attendee_id(user), datetime.now(UTC)
        )
    except service.EventNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found") from exc
    except service.RegistrationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found") from exc
    except service.WithdrawalNotAllowedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return WithdrawalRead.model_validate(registration).model_copy(
        update={"already_withdrawn": already_withdrawn}
    )
