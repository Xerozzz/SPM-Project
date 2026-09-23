"""Venue catalogue orchestration for SCRUM-59.

Each function loads what it needs and hands back the result. Every failure is a typed
exception so the router can map it to a status code without knowing any of the rules.
"""

import uuid

from core.database import Session
from models.venue import Venue
from repositories import venues as repo


class VenueError(Exception):
    """Base class for every refusal this service raises."""


class VenueNotFoundError(VenueError):
    """No venue with that id."""


def list_selectable(db: Session) -> list[Venue]:
    """AC3: the venues a coordinator may choose for new work."""
    return repo.list_active(db)


def get(db: Session, venue_id: uuid.UUID) -> Venue:
    """AC4: one venue, active or not, so historical references stay readable."""
    venue = repo.get(db, venue_id)
    if venue is None:
        raise VenueNotFoundError
    return venue
