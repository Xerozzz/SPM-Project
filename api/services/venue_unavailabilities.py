"""Venue-unavailability orchestration for SCRUM-62."""

import uuid

from core.database import Session
from domain.validation import FieldProblem
from domain.venue_unavailability import VenueUnavailabilityFields, validate_unavailability
from models.venue_unavailability import VenueUnavailability
from repositories import venue_unavailabilities as repo
from services import venues


class VenueUnavailabilityError(Exception):
    """Base class for closures the service cannot perform."""


class VenueUnavailabilityNotFoundError(VenueUnavailabilityError):
    """The named closure does not exist at this venue."""


class InactiveVenueError(VenueUnavailabilityError):
    """New closure records only make sense for selectable venues."""


class InvalidVenueUnavailabilityError(VenueUnavailabilityError):
    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("the unavailability period is not valid")
        self.problems = problems


def list_for_venue(db: Session, venue_id: uuid.UUID) -> list[VenueUnavailability]:
    venues.get(db, venue_id)
    return repo.list_for_venue(db, venue_id)


def create(
    db: Session, venue_id: uuid.UUID, fields: VenueUnavailabilityFields
) -> VenueUnavailability:
    venue = venues.get(db, venue_id)
    if not venue.is_active:
        raise InactiveVenueError
    _ensure_valid(fields)
    return repo.save(db, VenueUnavailability(venue_id=venue_id, **_stored_values(fields)))


def update(
    db: Session,
    venue_id: uuid.UUID,
    unavailability_id: uuid.UUID,
    fields: VenueUnavailabilityFields,
) -> VenueUnavailability:
    record = _get_for_venue(db, venue_id, unavailability_id)
    _ensure_valid(fields)
    for name, value in _stored_values(fields).items():
        setattr(record, name, value)
    return repo.save(db, record)


def delete(db: Session, venue_id: uuid.UUID, unavailability_id: uuid.UUID) -> None:
    repo.delete(db, _get_for_venue(db, venue_id, unavailability_id))


def _get_for_venue(
    db: Session, venue_id: uuid.UUID, unavailability_id: uuid.UUID
) -> VenueUnavailability:
    record = repo.get(db, unavailability_id)
    if record is None or record.venue_id != venue_id:
        raise VenueUnavailabilityNotFoundError
    return record


def _ensure_valid(fields: VenueUnavailabilityFields) -> None:
    problems = validate_unavailability(fields)
    if problems:
        raise InvalidVenueUnavailabilityError(problems)


def _stored_values(fields: VenueUnavailabilityFields) -> dict[str, object]:
    assert fields.starts_at is not None
    assert fields.ends_at is not None
    assert fields.reason is not None
    return {
        "starts_at": fields.starts_at,
        "ends_at": fields.ends_at,
        "reason": fields.reason.strip(),
    }
