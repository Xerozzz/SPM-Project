"""Attendee registration endpoints: HTTP/auth only."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_role
from domain.roles import Role
from schemas.event_registrations import AttendeeEventRead, RegistrationRead, RegistrationSubmit
from services import event_registrations as service

router = APIRouter(prefix="/attendee", tags=["attendee-registrations"])
Attendee = Annotated[dict[str, object], Depends(require_role(Role.ATTENDEE))]
Db = Annotated[Session, Depends(get_db)]


def _attendee_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


@router.get("/events", response_model=list[AttendeeEventRead])
def list_events(_user: Attendee, db: Db) -> list[AttendeeEventRead]:
    events = service.list_open_events(db, datetime.now(UTC))
    return [AttendeeEventRead.model_validate(event) for event in events]


@router.get("/events/{event_id}", response_model=AttendeeEventRead)
def read_event(event_id: uuid.UUID, _user: Attendee, db: Db) -> AttendeeEventRead:
    try:
        event = service.event_for_registration(db, event_id, datetime.now(UTC))
    except service.EventNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Event is not open for registration"
        ) from exc
    return AttendeeEventRead.model_validate(event)


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
