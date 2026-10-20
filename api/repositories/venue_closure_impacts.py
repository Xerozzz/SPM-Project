"""Database access for venue closure impact snapshots (SCRUM-81)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.venue_closure_impact import VenueClosureImpact


def stage(db: Session, impact: VenueClosureImpact) -> None:
    """Add without committing: the caller's commit saves it with the closure (AC8)."""
    db.add(impact)


def list_for_closure(db: Session, unavailability_id: uuid.UUID) -> list[VenueClosureImpact]:
    """Every impact snapshot a closure produced, oldest first."""
    statement = (
        select(VenueClosureImpact)
        .where(VenueClosureImpact.unavailability_id == unavailability_id)
        .order_by(VenueClosureImpact.recorded_at, VenueClosureImpact.id)
    )
    return list(db.scalars(statement))
