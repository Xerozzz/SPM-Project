"""HTTP endpoints for Venue Staff closure management (SCRUM-62)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_user, require_role
from domain.roles import Role
from domain.venue_unavailability import VenueUnavailabilityFields
from schemas.venue_unavailabilities import (
    AffectedArrangementRead,
    VenueUnavailabilityRead,
    VenueUnavailabilitySaved,
    VenueUnavailabilityWrite,
)
from services import venue_unavailabilities as service
from services import venues

router = APIRouter(prefix="/venues/{venue_id}/unavailabilities", tags=["venue-unavailability"])

VenueStaff = Annotated[dict[str, object], Depends(require_role(Role.VENUE_STAFF))]
AnyUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, venues.VenueNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    if isinstance(exc, service.VenueUnavailabilityNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Venue unavailability not found")
    if isinstance(exc, service.InactiveVenueError):
        return HTTPException(status.HTTP_409_CONFLICT, "Venue is not active")
    assert isinstance(exc, service.InvalidVenueUnavailabilityError)
    return HTTPException(422, [problem.__dict__ for problem in exc.problems])


@router.get("", response_model=list[VenueUnavailabilityRead])
def list_records(venue_id: uuid.UUID, user: AnyUser, db: Db) -> list[VenueUnavailabilityRead]:
    del user
    try:
        records = service.list_for_venue(db, venue_id)
        return [VenueUnavailabilityRead.model_validate(row) for row in records]
    except venues.VenueNotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("", response_model=VenueUnavailabilitySaved, status_code=status.HTTP_201_CREATED)
def create_record(
    venue_id: uuid.UUID, body: VenueUnavailabilityWrite, user: VenueStaff, db: Db
) -> VenueUnavailabilitySaved:
    fields = VenueUnavailabilityFields(**body.model_dump())
    try:
        saved = service.create(db, venue_id, fields, _user_id(user), datetime.now(UTC))
    except (venues.VenueNotFoundError, service.VenueUnavailabilityError) as exc:
        raise _http_error(exc) from exc
    return _saved(saved)


@router.put("/{unavailability_id}", response_model=VenueUnavailabilitySaved)
def update_record(
    venue_id: uuid.UUID,
    unavailability_id: uuid.UUID,
    body: VenueUnavailabilityWrite,
    user: VenueStaff,
    db: Db,
) -> VenueUnavailabilitySaved:
    fields = VenueUnavailabilityFields(**body.model_dump())
    try:
        saved = service.update(
            db, venue_id, unavailability_id, fields, _user_id(user), datetime.now(UTC)
        )
    except service.VenueUnavailabilityError as exc:
        raise _http_error(exc) from exc
    return _saved(saved)


@router.delete("/{unavailability_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    venue_id: uuid.UUID, unavailability_id: uuid.UUID, user: VenueStaff, db: Db
) -> Response:
    del user
    try:
        service.delete(db, venue_id, unavailability_id)
    except service.VenueUnavailabilityError as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


def _saved(saved: service.SavedClosure) -> VenueUnavailabilitySaved:
    """SCRUM-81 AC2: the closure and the arrangements it affects, for Venue Staff."""
    read = VenueUnavailabilityRead.model_validate(saved.record)
    affected = [
        AffectedArrangementRead(
            booking_id=item.booking.id,
            event_request_id=item.booking.event_request_id,
            event_name=item.event.name if item.event else None,
            session_label=item.booking.session_label,
            start_at=item.booking.start_at,
            end_at=item.booking.end_at,
            status=item.booking.status,
        )
        for item in saved.affected
    ]
    return VenueUnavailabilitySaved(**read.model_dump(), affected=affected)
