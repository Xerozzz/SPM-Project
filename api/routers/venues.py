"""HTTP endpoints for reading the venue catalogue (SCRUM-59).

Every signed-in user may read it. Venue Staff maintain it; those endpoints land with the
stories that add them. Authorisation uses the shared dependency, never an inline role
check (AGENTS.md section 3).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_user
from schemas.venues import VenueRead
from services import venues as service

router = APIRouter(prefix="/venues", tags=["venues"])

AnyUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]

_REFUSALS = (service.VenueError,)


def _http_error(exc: Exception) -> HTTPException:
    """The single mapping from refusals to status codes, shared by every route here."""
    # VenueNotFoundError is the only refusal this router can meet today. A second one
    # added later fails here loudly rather than falling through to a status nobody chose.
    assert isinstance(exc, service.VenueNotFoundError)
    return HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")


@router.get("", response_model=list[VenueRead])
def list_selectable(user: AnyUser, db: Db) -> list[VenueRead]:
    """The venues that may be chosen for new work (AC2, AC3)."""
    del user
    return [VenueRead.model_validate(row) for row in service.list_selectable(db)]


@router.get("/{venue_id}", response_model=VenueRead)
def read(venue_id: uuid.UUID, user: AnyUser, db: Db) -> VenueRead:
    """One venue, active or not, so an existing event that names it stays readable (AC4)."""
    del user
    try:
        return VenueRead.model_validate(service.get(db, venue_id))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
