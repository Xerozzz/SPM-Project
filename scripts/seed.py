#!/usr/bin/env python3
"""Seed local development data. Run with `make seed`; the api container also runs it on
every start, so a fresh `docker compose up` is immediately usable.

- One supplied user per role (SCRUM-27, F1). Never modified once created.
- Two sample event requests for organiser@example.com (SCRUM-46): one complete draft
  and one with gaps, so both the happy path and the field-error path can be demonstrated.
  These are *reset to Draft on every run* — they are demo data, not user data.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.security import hash_password
from domain.event_status import EventStatus
from models.event_request import EventRequest
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


def _sample_event_requests() -> list[dict[str, object]]:
    start = (datetime.now(UTC) + timedelta(days=30)).replace(minute=0, second=0, microsecond=0)
    return [
        {
            "name": "Orientation Day",
            "purpose": "Welcome new students to the faculty",
            "description": "Half-day programme with talks, a Q&A panel and a campus tour.",
            "start_at": start,
            "end_at": start + timedelta(hours=4),
            "expected_attendance": 200,
            "venue_requirement": "Auditorium seating at least 200",
            "accessibility_requirement": "Step-free access and a hearing loop",
            "equipment_requirement": "Projector, two handheld microphones",
            "layout_requirement": "Theatre style",
            "registration_requirement": "Open registration, capped at 200",
        },
        {
            # Deliberately incomplete: submitting this shows the field errors (AC2).
            "name": "Hackathon (draft)",
            "purpose": "48-hour student hackathon",
            "description": None,
            "start_at": start + timedelta(days=14),
            "end_at": None,
            "expected_attendance": None,
            "venue_requirement": "Large open-plan space with power at every table",
            "accessibility_requirement": None,
            "equipment_requirement": None,
            "layout_requirement": None,
            "registration_requirement": None,
        },
    ]


def _seed_users(db: Session) -> None:
    """Insert missing seed users; never touch existing rows."""
    for email, password, roles in _SEED_USERS:
        if users_repo.get_by_email(db, email) is None:
            db.add(User(email=email, password_hash=hash_password(password), roles=roles))


def _seed_event_requests(db: Session) -> None:
    """Create the sample requests, or reset them to Draft if they already exist."""
    organiser = users_repo.get_by_email(db, "organiser@example.com")
    if organiser is None:
        return
    for sample in _sample_event_requests():
        existing = db.scalars(
            select(EventRequest).where(
                EventRequest.organiser_id == organiser.id, EventRequest.name == sample["name"]
            )
        ).first()
        request = existing or EventRequest(organiser_id=organiser.id)
        for field, value in sample.items():
            setattr(request, field, value)
        request.status = EventStatus.DRAFT
        request.submitted_at = None
        db.add(request)


def main() -> None:
    db = SessionLocal()
    try:
        _seed_users(db)
        db.flush()
        _seed_event_requests(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
