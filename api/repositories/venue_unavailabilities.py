"""Database queries for venue closure periods (SCRUM-62)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.venue_unavailability import VenueUnavailability


def get(db: Session, unavailability_id: uuid.UUID) -> VenueUnavailability | None:
    return db.get(VenueUnavailability, unavailability_id)


def list_for_venue(db: Session, venue_id: uuid.UUID) -> list[VenueUnavailability]:
    statement = (
        select(VenueUnavailability)
        .where(VenueUnavailability.venue_id == venue_id)
        .order_by(VenueUnavailability.starts_at, VenueUnavailability.id)
    )
    return list(db.scalars(statement))


def save(db: Session, record: VenueUnavailability) -> VenueUnavailability:
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def delete(db: Session, record: VenueUnavailability) -> None:
    db.delete(record)
    db.commit()


def stage(db: Session, record: VenueUnavailability) -> VenueUnavailability:
    """SCRUM-81: add or update without committing, so the caller commits the closure, its
    impact record and its notifications together (AC8)."""
    db.add(record)
    db.flush()
    return record
