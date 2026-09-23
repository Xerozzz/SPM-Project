"""HTTP endpoints for the venue catalogue (SCRUM-59).

Venue Staff maintain the catalogue; every signed-in user may read it. The split is done
with the shared role dependency, never with an inline role check (AGENTS.md section 3).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_user, require_role
from domain.roles import Role
from domain.venue import VenueFields
from schemas.venues import VenueCreate, VenueProblemRead, VenueRead, VenueUpdate
from services import venues as service

router = APIRouter(prefix="/venues", tags=["venues"])

VenueStaff = Annotated[dict[str, object], Depends(require_role(Role.VENUE_STAFF))]
AnyUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]

_REFUSALS = (service.VenueError,)


def _http_error(exc: Exception) -> HTTPException:
    """The single mapping from refusals to status codes, shared by every route here."""
    if isinstance(exc, service.VenueNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    if isinstance(exc, service.DuplicateVenueNameError):
        return HTTPException(status.HTTP_409_CONFLICT, "A venue with that name already exists")
    # InvalidVenueError is the only refusal left: VenueError has exactly these three
    # subclasses. A fourth added later fails here loudly rather than falling through to a
    # status code nobody chose.
    assert isinstance(exc, service.InvalidVenueError)
    problems = [VenueProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
    # A literal 422, as in routers/event_requests.py: Starlette renamed its constant
    # between the versions we allow.
    return HTTPException(422, [p.model_dump() for p in problems])


@router.get("", response_model=list[VenueRead])
def list_selectable(user: AnyUser, db: Db) -> list[VenueRead]:
    """The venues that may be chosen for new work (AC2, AC3)."""
    del user
    return [VenueRead.model_validate(row) for row in service.list_selectable(db)]


@router.get("/all", response_model=list[VenueRead])
def list_for_staff(user: VenueStaff, db: Db) -> list[VenueRead]:
    """Every venue including deactivated ones, for the staff who maintain the catalogue."""
    del user
    return [VenueRead.model_validate(row) for row in service.list_for_staff(db)]


@router.get("/{venue_id}", response_model=VenueRead)
def read(venue_id: uuid.UUID, user: AnyUser, db: Db) -> VenueRead:
    """One venue, active or not, so an existing event or booking stays readable (AC4)."""
    del user
    try:
        return VenueRead.model_validate(service.get(db, venue_id))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc


@router.post("", response_model=VenueRead, status_code=status.HTTP_201_CREATED)
def create(body: VenueCreate, user: VenueStaff, db: Db) -> VenueRead:
    """Add a venue to the catalogue (AC1); 422 names the fields to fix (AC5)."""
    del user
    try:
        return VenueRead.model_validate(service.create(db, VenueFields(**body.model_dump())))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc


@router.patch("/{venue_id}", response_model=VenueRead)
def update(venue_id: uuid.UUID, body: VenueUpdate, user: VenueStaff, db: Db) -> VenueRead:
    """Change a venue's details (AC1); an invalid change saves nothing (AC5)."""
    del user
    try:
        return VenueRead.model_validate(
            service.update(db, venue_id, body.model_dump(exclude_unset=True))
        )
    except _REFUSALS as exc:
        raise _http_error(exc) from exc


@router.post("/{venue_id}/deactivate", response_model=VenueRead)
def deactivate(venue_id: uuid.UUID, user: VenueStaff, db: Db) -> VenueRead:
    """Take a venue out of the selectable catalogue without deleting it (AC3, ADR-0012)."""
    del user
    try:
        return VenueRead.model_validate(service.deactivate(db, venue_id))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc


@router.post("/{venue_id}/reactivate", response_model=VenueRead)
def reactivate(venue_id: uuid.UUID, user: VenueStaff, db: Db) -> VenueRead:
    """Put a venue back in the catalogue once it is available again."""
    del user
    try:
        return VenueRead.model_validate(service.reactivate(db, venue_id))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
