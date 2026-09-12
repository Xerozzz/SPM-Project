"""User lookups. The only layer that queries the users table (ADR-0003)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.user import User


def get_by_email(db: Session, email: str) -> User | None:
    """Return the user with this email, or None."""
    return db.scalars(select(User).where(User.email == email)).first()
