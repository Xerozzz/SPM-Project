"""SCRUM-113 registration intake settings: HTTP/auth only."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import EventAccess, require_event_access
from domain.registration_intake import RegistrationIntakeError
from models.event_request import EventRequest
from schemas.registration_intake import (
    RegistrationExtension,
    RegistrationOpen,
    RegistrationSettingsRead,
)
from services import registration_intake as service

router = APIRouter(prefix="/event-requests", tags=["registration-intake"])
ReadableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.READ_REGISTRATION_SETTINGS))
]
ManageableEvent = Annotated[
    EventRequest, Depends(require_event_access(EventAccess.MANAGE_REGISTRATION))
]
Db = Annotated[Session, Depends(get_db)]


def _refusal(exc: RegistrationIntakeError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/{request_id}/registration", response_model=RegistrationSettingsRead)
def read_settings(event: ReadableEvent) -> RegistrationSettingsRead:
    return RegistrationSettingsRead.of(event, datetime.now(UTC))


@router.post("/{request_id}/registration/open", response_model=RegistrationSettingsRead)
def open_settings(
    event: ManageableEvent, body: RegistrationOpen, db: Db
) -> RegistrationSettingsRead:
    now = datetime.now(UTC)
    try:
        opened = service.open_intake(db, event.id, body.closes_at, now)
    except RegistrationIntakeError as exc:
        raise _refusal(exc) from exc
    return RegistrationSettingsRead.of(opened, now)


@router.post("/{request_id}/registration/extend", response_model=RegistrationSettingsRead)
def extend_settings(
    event: ManageableEvent, body: RegistrationExtension, db: Db
) -> RegistrationSettingsRead:
    now = datetime.now(UTC)
    try:
        extended = service.extend_intake(db, event.id, body.closes_at, now)
    except RegistrationIntakeError as exc:
        raise _refusal(exc) from exc
    return RegistrationSettingsRead.of(extended, now)
