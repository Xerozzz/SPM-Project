"""Database access for equipment catalogue entries (SCRUM-84)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.equipment import Equipment


def get_by_type_and_location(db: Session, equipment_type: str, location: str) -> Equipment | None:
    """Return the entry at this type-and-location combination, if one exists."""
    statement = select(Equipment).where(
        Equipment.equipment_type == equipment_type.strip(), Equipment.location == location.strip()
    )
    return db.scalars(statement).first()


def list_all(db: Session) -> list[Equipment]:
    """Return the catalogue in a stable, readable order."""
    statement = select(Equipment).order_by(Equipment.equipment_type, Equipment.location)
    return list(db.scalars(statement))


def save(db: Session, equipment: Equipment) -> Equipment:
    """Commit a new entry and refresh values set by the database."""
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment
