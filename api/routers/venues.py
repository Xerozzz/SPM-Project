"""HTTP endpoints for the venue catalogue (SCRUM-59) and venue search (SCRUM-55).

Venue Staff maintain the catalogue; every signed-in user may read it. Venue search is
coordinator-only. The split is done with the shared role dependency, never with an
inline role check (AGENTS.md section 3).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_user, require_role
from domain.roles import Role
from domain.venue import VenueFields
from schemas.venue_booking_decisions import ConflictRead
from schemas.venues import (
    BufferChangeRead,
    ProblemBookingRead,
    VenueCreate,
    VenueProblemRead,
    VenueProblemsRead,
    VenueRead,
    VenueUpdate,
    VenueUpdateRead,
)
from services import venue_buffer_review as buffer_review
from services import venue_search as search_service
from services import venues as service

router = APIRouter(prefix="/venues", tags=["venues"])

VenueStaff = Annotated[dict[str, object], Depends(require_role(Role.VENUE_STAFF))]
Coordinator = Annotated[dict[str, object], Depends(require_role(Role.COORDINATOR))]
AnyUser = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]

_REFUSALS = (service.VenueError,)


def _problem_read(problem: buffer_review.ReviewedBooking) -> ProblemBookingRead:
    """One problematic booking as the API reports it, wherever it is reported."""
    return ProblemBookingRead(
        booking_id=problem.booking.id,
        event_request_id=problem.booking.event_request_id,
        event_name=problem.event.name if problem.event is not None else None,
        start_at=problem.booking.start_at,
        end_at=problem.booking.end_at,
        conflict=ConflictRead.from_error(problem.conflict, buffer_review.buffers_of(problem.venue)),
    )


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


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


@router.get("/search", response_model=list[VenueRead])
def search(
    user: Coordinator,
    db: Db,
    start_at: datetime,
    end_at: datetime,
    minimum_capacity: Annotated[int | None, Query(ge=1)] = None,
    location: str | None = None,
    accessibility: Annotated[list[str] | None, Query()] = None,
    facility: Annotated[list[str] | None, Query()] = None,
    layout: str | None = None,
) -> list[VenueRead]:
    """SCRUM-55: active venues satisfying every criterion and free for the period."""
    del user
    problems = _search_period_problems(start_at, end_at)
    if problems:
        raise HTTPException(422, problems)
    rows = search_service.search(
        db,
        start_at=start_at,
        end_at=end_at,
        minimum_capacity=minimum_capacity,
        location=location,
        accessibility=accessibility,
        facility=facility,
        layout=layout,
    )
    return [VenueRead.model_validate(row) for row in rows]


def _search_period_problems(start_at: datetime, end_at: datetime) -> list[dict[str, str]]:
    """422 problems for a requested period FastAPI parsed but the domain rejects.

    A naive datetime (no offset) parses fine but has no instant behind it, so the
    domain raises ValueError; report it here in the same FieldProblem shape the
    catalogue uses (SCRUM-59/SCRUM-62) instead of letting it become a 500.

    A period that has already ended is refused for the same reason SCRUM-62 refuses an
    elapsed closure: nothing can be booked into it, so answering with a list of venues
    tells the coordinator something untrue. The rule is on the end, not the start, so a
    slot that is already running can still be searched for.
    """
    problems: list[dict[str, str]] = []
    if start_at.tzinfo is None:
        problems.append({"field": "start_at", "reason": "must be given in UTC"})
    if end_at.tzinfo is None:
        problems.append({"field": "end_at", "reason": "must be given in UTC"})
    if problems:
        return problems
    if end_at <= start_at:
        problems.append({"field": "end_at", "reason": "must be after the start time"})
    elif end_at <= datetime.now(UTC):
        problems.append({"field": "end_at", "reason": "must be in the future"})
    return problems


@router.get("/booking-problems", response_model=list[VenueProblemsRead])
def booking_problems(user: VenueStaff, db: Db) -> list[VenueProblemsRead]:
    """SCRUM-89 AC4: every booking anywhere that cannot stand under its venue's buffers.

    Declared before `/{venue_id}` so "booking-problems" is not read as a venue id.

    Computed on each request rather than read from a stored marker, so it is right the
    moment it is asked and needs nothing to clear it when a buffer is lowered or a
    clashing booking is cancelled (AC3, AC7).
    """
    del user
    return [
        VenueProblemsRead(
            venue_id=entry.venue.id,
            venue_name=entry.venue.name,
            venue_location=entry.venue.location,
            setup_minutes=entry.venue.setup_minutes,
            turnaround_minutes=entry.venue.turnaround_minutes,
            is_active=entry.venue.is_active,
            problems=[_problem_read(problem) for problem in entry.problems],
        )
        for entry in buffer_review.review_every_venue(db, datetime.now(UTC))
    ]


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


@router.post("", response_model=VenueRead, status_code=status.HTTP_201_CREATED)
def create(body: VenueCreate, user: VenueStaff, db: Db) -> VenueRead:
    """Add a venue to the catalogue (AC1); 422 names the fields to fix (AC5)."""
    del user
    try:
        return VenueRead.model_validate(service.create(db, VenueFields(**body.model_dump())))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc


@router.patch("/{venue_id}", response_model=VenueUpdateRead)
def update(venue_id: uuid.UUID, body: VenueUpdate, user: VenueStaff, db: Db) -> VenueUpdateRead:
    """Change a venue's details (AC1); an invalid change saves nothing (AC5).

    SCRUM-89 AC6: when the change moved the venue's buffers, the response also says which
    existing bookings that made problematic, or that none were.
    """
    try:
        venue, result = service.update(
            db, venue_id, body.model_dump(exclude_unset=True), _user_id(user), datetime.now(UTC)
        )
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
    return VenueUpdateRead(
        **VenueRead.model_validate(venue).model_dump(),
        buffer_change=BufferChangeRead(
            changed=result.changed,
            problems=[_problem_read(problem) for problem in result.problems],
        ),
    )


@router.post("/{venue_id}/deactivate", response_model=VenueRead)
def deactivate(venue_id: uuid.UUID, user: VenueStaff, db: Db) -> VenueRead:
    """Take a venue out of the selectable catalogue without deleting it (AC3, ADR-0012)."""
    del user
    try:
        return VenueRead.model_validate(service.deactivate(db, venue_id))
    except _REFUSALS as exc:
        raise _http_error(exc) from exc
