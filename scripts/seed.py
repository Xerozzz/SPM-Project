#!/usr/bin/env python3
"""Seed one supplied user per role for local development (SCRUM-27, F1).

Idempotent: safe to run repeatedly. Run with `make seed`.
"""

from core.database import SessionLocal
from core.security import hash_password
from models.user import User
from repositories import users as users_repo

_SEED_USERS: list[tuple[str, str, list[str]]] = [
    ("organiser@example.com", "password123", ["organiser"]),
    ("coordinator@example.com", "password123", ["coordinator"]),
    ("venue-staff@example.com", "password123", ["venue_staff"]),
    ("tech-support@example.com", "password123", ["tech_support"]),
    ("attendee@example.com", "password123", ["attendee"]),
    ("multi-role@example.com", "password123", ["organiser", "coordinator"]),
]


def main() -> None:
    """Insert missing seed users; never touch existing rows."""
    db = SessionLocal()
    try:
        for email, password, roles in _SEED_USERS:
            if users_repo.get_by_email(db, email) is None:
                db.add(User(email=email, password_hash=hash_password(password), roles=roles))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
