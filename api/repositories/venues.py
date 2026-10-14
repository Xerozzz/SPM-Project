"""Venue catalogue queries. The only layer that touches the venues table (ADR-0003)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.venue import Venue


def get(db: Session, venue_id: uuid.UUID) -> Venue | None:
    """Return the venue with this id whatever its state, or None.

    Deliberately does not filter on `is_active`: AC4 needs a deactivated venue to stay
    readable for the events and bookings that already reference it.
    """
    return db.get(Venue, venue_id)


def get_by_name(db: Session, name: str) -> Venue | None:
    """Return the venue with this name, or None.

    AC1 requires the name to be unique. Checking here rather than letting the database's
    unique constraint fire gives the caller a named field instead of an integrity error.
    """
    return db.scalars(select(Venue).where(Venue.name == name.strip())).first()


def list_active(db: Session) -> list[Venue]:
    """Venues that may be chosen for new work, by name (AC3)."""
    statement = select(Venue).where(Venue.is_active.is_(True)).order_by(Venue.name)
    return list(db.scalars(statement))


def list_all(db: Session) -> list[Venue]:
    """Every venue, active or not, by name (SCRUM-89).

    Unlike `list_active`, this includes deactivated venues. A venue taken out of the
    catalogue under ADR-0012 keeps the bookings already made for it, and those are the
    ones least likely to be looked at, so a review that skipped them would hide exactly
    the problems most likely to be missed.
    """
    return list(db.scalars(select(Venue).order_by(Venue.name)))


def save(db: Session, venue: Venue) -> Venue:
    """Commit the venue's pending changes and reload it with database-set values."""
    db.add(venue)
    db.commit()
    db.refresh(venue)
    return venue
