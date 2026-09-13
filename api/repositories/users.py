"""User lookups. The only layer that queries the users table (ADR-0003)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.roles import Role
from models.user import User


def get_by_email(db: Session, email: str) -> User | None:
    """Return the user with this email, or None."""
    return db.scalars(select(User).where(User.email == email)).first()


def list_active_coordinators(db: Session) -> list[User]:
    """Active Event Coordinators, ordered by account creation — SCRUM-34's fixed
    rotation order for round-robin assignment."""
    stmt = (
        select(User)
        .where(User.roles.contains([Role.COORDINATOR.value]), User.is_active.is_(True))
        .order_by(User.created_at, User.id)
    )
    return list(db.scalars(stmt))
