#!/usr/bin/env python3
"""Seed local development data. Run with `make seed`; the api container also runs it on
every start, so a fresh `docker compose up` is immediately usable.

- One supplied user per role (SCRUM-27, F1). Never modified once created.
- Two sample event requests for organiser@example.com (SCRUM-46): one complete draft
  and one with gaps, so both the happy path and the field-error path can be demonstrated.
  These are *reset to Draft on every run* — they are demo data, not user data.
"""

import uuid
from datetime import UTC, datetime, timedelta

from core.database import Session, SessionLocal
from core.security import hash_password
from domain.roles import Role
from models.event_request import EventRequest
from models.user import User
from repositories import event_requests as event_requests_repo
from repositories import users as users_repo

_SEED_USERS: list[tuple[str, str, list[Role]]] = [
    ("organiser@example.com", "password123", [Role.ORGANISER]),
    ("coordinator@example.com", "password123", [Role.COORDINATOR]),
    # A second active coordinator, so a fresh `docker compose up` can demonstrate
    # round-robin assignment (SCRUM-34) rather than always assigning the same one.
    ("coordinator2@example.com", "password123", [Role.COORDINATOR]),
    ("venue-staff@example.com", "password123", [Role.VENUE_STAFF]),
    ("tech-support@example.com", "password123", [Role.TECH_SUPPORT]),
    ("attendee@example.com", "password123", [Role.ATTENDEE]),
    ("multi-role@example.com", "password123", [Role.ORGANISER, Role.COORDINATOR]),
]


# Fixed ids, so the samples can be found and replaced no matter what an organiser has
# renamed them to in the meantime. The rows are demo data: they are deleted and recreated
# on every seed run, which is also why the seed never assigns a status — a fresh row is a
# draft by construction, and only domain/event_status.py may move it from there.
_SAMPLE_IDS = (
    uuid.UUID("00000000-0000-4000-8000-000000000001"),
    uuid.UUID("00000000-0000-4000-8000-000000000002"),
)


def _sample_event_requests() -> list[tuple[uuid.UUID, dict[str, object]]]:
    start = (datetime.now(UTC) + timedelta(days=30)).replace(minute=0, second=0, microsecond=0)
    orientation_day: dict[str, object] = {
        "name": "Orientation Day",
        "purpose": "Welcome new students to the faculty",
        "description": "Half-day programme with talks, a Q&A panel and a campus tour.",
        "start_at": start,
        "end_at": start + timedelta(hours=4),
        "expected_attendance": 200,
        "venue_requirement": "Auditorium-type venue",
        "accessibility_requirement": "Step-free access and a hearing loop",
        "equipment_requirement": "Projector-type requirement",
        "layout_requirement": "Theatre style",
        "registration_requirement": "Open registration, capped at 200",
    }
    # Deliberately incomplete: submitting this shows the field errors (AC2).
    hackathon: dict[str, object] = {
        "name": "Hackathon (draft)",
        "purpose": "48-hour student hackathon",
        "description": None,
        "start_at": start + timedelta(days=14),
        "end_at": None,
        "expected_attendance": None,
        "venue_requirement": "Outdoor event space",
        "accessibility_requirement": None,
        "equipment_requirement": None,
        "layout_requirement": None,
        "registration_requirement": None,
    }
    return [(_SAMPLE_IDS[0], orientation_day), (_SAMPLE_IDS[1], hackathon)]


def _seed_users(db: Session) -> None:
    """Insert missing seed users; never touch existing rows."""
    for email, password, roles in _SEED_USERS:
        if users_repo.get_by_email(db, email) is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    roles=[role.value for role in roles],
                )
            )


def _seed_event_requests(db: Session) -> None:
    """Replace the sample requests so they are back in Draft, whatever happened to them."""
    organiser = users_repo.get_by_email(db, "organiser@example.com")
    if organiser is None:
        return
    for sample_id, fields in _sample_event_requests():
        existing = event_requests_repo.get(db, sample_id)
        if existing is not None:
            event_requests_repo.delete(db, existing)
            db.flush()
        event_requests_repo.add(db, EventRequest(id=sample_id, organiser_id=organiser.id, **fields))


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
