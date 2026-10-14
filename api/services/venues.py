"""Venue catalogue orchestration for SCRUM-59.

Each function loads what it needs, asks the domain layer whether the data is valid, and
persists the outcome. Every failure is a typed exception so the router can map it to a
status code without knowing any of the rules.
"""

import uuid
from datetime import datetime
from typing import Any

from core.database import Session
from domain.validation import FieldProblem
from domain.venue import BUFFER_FIELDS, VenueFields, field_names, validate_venue
from models.venue import Venue
from repositories import venues as repo
from services import venue_buffer_review as buffer_review


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


def list_selectable_names(db: Session) -> list[str]:
    """Active venue names organisers may record as a requirement."""
    return [venue.name for venue in repo.list_active(db)]


def get(db: Session, venue_id: uuid.UUID) -> Venue:
    """AC4: one venue, active or not, so historical references stay readable."""
    venue = repo.get(db, venue_id)
    if venue is None:
        raise VenueNotFoundError
    return venue


def create(db: Session, fields: VenueFields) -> Venue:
    """AC1: store a new venue once its data is valid and its name is unused."""
    _ensure_valid(fields)
    _ensure_name_is_free(db, fields.name, replacing=None)
    venue = Venue(**_stored_values(fields))
    return repo.save(db, venue)


def update(
    db: Session,
    venue_id: uuid.UUID,
    changes: dict[str, object],
    changed_by_id: uuid.UUID,
    now: datetime,
) -> tuple[Venue, buffer_review.BufferChangeResult]:
    """AC1: change a venue's details. AC5: an invalid change saves nothing at all.

    SCRUM-89: a change to the setup or turnaround time is also re-assessed and recorded,
    in the same commit as the change itself, so a rolled back change leaves no audit row
    claiming it happened. The result says whether the buffers moved and what that caught
    out, which is what the route tells Venue Staff (SCRUM-89 AC6).
    """
    venue = get(db, venue_id)
    previous_buffers = buffer_review.buffers_of(venue)
    # Validate the record as it would be after the change, not the change on its own, so
    # clearing a required field is caught even though the field is absent from the payload.
    merged_values: dict[str, Any] = {
        name: changes.get(name, getattr(venue, name)) for name in field_names()
    }
    merged = VenueFields(**merged_values)
    _ensure_valid(merged)
    _ensure_name_is_free(db, merged.name, replacing=venue.id)

    for name, value in _stored_values(merged).items():
        setattr(venue, name, value)
    # Before the save, so both land together. Nothing here writes to a booking (AC5).
    result = buffer_review.record_change(db, venue, previous_buffers, changed_by_id, now)
    return repo.save(db, venue), result


def deactivate(db: Session, venue_id: uuid.UUID) -> Venue:
    """AC3: take a venue out of the selectable catalogue without deleting it (ADR-0012).

    Deactivating an already deactivated venue is not an error: the caller asked for a
    state, and the venue is already in it.
    """
    venue = get(db, venue_id)
    venue.is_active = False
    return repo.save(db, venue)


def _ensure_valid(fields: VenueFields) -> None:
    problems = validate_venue(fields)
    if problems:
        raise InvalidVenueError(problems)


def _ensure_name_is_free(db: Session, name: str | None, *, replacing: uuid.UUID | None) -> None:
    """`replacing` is the venue being updated, which is allowed to keep its own name."""
    assert name is not None  # _ensure_valid runs first and rejects a missing name.
    existing = repo.get_by_name(db, name)
    if existing is not None and existing.id != replacing:
        raise DuplicateVenueNameError


def _stored_values(fields: VenueFields) -> dict[str, object]:
    """The validated field values, with text trimmed and list fields never None."""
    values = {name: getattr(fields, name) for name in field_names()}
    for name in ("name", "location"):
        value = values[name]
        values[name] = value.strip() if isinstance(value, str) else value
    for name in ("facilities", "supported_layouts", "accessibility_features"):
        values[name] = values[name] or []
    # SCRUM-82: an absent buffer is no buffer. Stored as zero so the column stays NOT NULL
    # and the venue behaves exactly as it did before buffers existed (AC7).
    for name in BUFFER_FIELDS:
        values[name] = values[name] or 0
    return values
