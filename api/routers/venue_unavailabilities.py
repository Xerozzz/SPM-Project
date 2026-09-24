"""HTTP endpoints for Venue Staff closure management (SCRUM-62)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_user, require_role
from domain.roles import Role
from domain.venue_unavailability import VenueUnavailabilityFields
from schemas.venue_unavailabilities import VenueUnavailabilityRead, VenueUnavailabilityWrite
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


@router.post("", response_model=VenueUnavailabilityRead, status_code=status.HTTP_201_CREATED)
def create_record(
    venue_id: uuid.UUID, body: VenueUnavailabilityWrite, user: VenueStaff, db: Db
) -> VenueUnavailabilityRead:
    del user
    try:
        return VenueUnavailabilityRead.model_validate(
            service.create(db, venue_id, VenueUnavailabilityFields(**body.model_dump()))
        )
    except (venues.VenueNotFoundError, service.VenueUnavailabilityError) as exc:
        raise _http_error(exc) from exc


@router.put("/{unavailability_id}", response_model=VenueUnavailabilityRead)
def update_record(
    venue_id: uuid.UUID,
    unavailability_id: uuid.UUID,
    body: VenueUnavailabilityWrite,
    user: VenueStaff,
    db: Db,
) -> VenueUnavailabilityRead:
    del user
    try:
        return VenueUnavailabilityRead.model_validate(
            service.update(
                db, venue_id, unavailability_id, VenueUnavailabilityFields(**body.model_dump())
            )
        )
    except service.VenueUnavailabilityError as exc:
        raise _http_error(exc) from exc


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
