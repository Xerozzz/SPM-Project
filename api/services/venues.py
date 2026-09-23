"""Venue catalogue orchestration for SCRUM-59.

Each function loads what it needs, asks the domain layer whether the data is valid, and
persists the outcome. Every failure is a typed exception so the router can map it to a
status code without knowing any of the rules.
"""

import uuid

from core.database import Session
from domain.validation import FieldProblem
from domain.venue import VenueFields, field_names, validate_venue
from models.venue import Venue
from repositories import venues as repo


class VenueError(Exception):
    """Base class for every refusal this service raises."""


class VenueNotFoundError(VenueError):
    """No venue with that id."""


class DuplicateVenueNameError(VenueError):
    """AC1: a venue name identifies one space, so it cannot be reused."""


class InvalidVenueError(VenueError):
    """AC5: the record cannot be saved until these fields are fixed."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("the venue is not valid")
        self.problems = problems


def list_selectable(db: Session) -> list[Venue]:
    """AC3: the venues a coordinator may choose for new work."""
    return repo.list_active(db)


def get(db: Session, venue_id: uuid.UUID) -> Venue:
    """AC4: one venue, active or not, so historical references stay readable."""
    venue = repo.get(db, venue_id)
    if venue is None:
        raise VenueNotFoundError
    return venue


def create(db: Session, fields: VenueFields) -> Venue:
    """AC1: store a new venue once its data is valid and its name is unused."""
    _ensure_valid(fields)
    _ensure_name_is_free(db, fields.name)
    venue = Venue(**_stored_values(fields))
    return repo.save(db, venue)


def _ensure_valid(fields: VenueFields) -> None:
    problems = validate_venue(fields)
    if problems:
        raise InvalidVenueError(problems)


def _ensure_name_is_free(db: Session, name: str | None) -> None:
    assert name is not None  # _ensure_valid runs first and rejects a missing name.
    if repo.get_by_name(db, name) is not None:
        raise DuplicateVenueNameError


def _stored_values(fields: VenueFields) -> dict[str, object]:
    """The validated field values, with text trimmed and list fields never None."""
    values = {name: getattr(fields, name) for name in field_names()}
    for name in ("name", "location"):
        value = values[name]
        values[name] = value.strip() if isinstance(value, str) else value
    for name in ("facilities", "supported_layouts", "accessibility_features"):
        values[name] = values[name] or []
    return values
