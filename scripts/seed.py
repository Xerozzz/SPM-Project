#!/usr/bin/env python3
"""Seed local development data. Run with `make seed`; the api container also runs it on
every start, so a fresh `docker compose up` is immediately usable.

- One supplied user per role (SCRUM-27, F1). Never modified once created.
- Four sample event requests for organiser@example.com (SCRUM-46): one complete draft, one
  with gaps so the field-error path can be demonstrated, one driven all the way to Approved
  so the venue booking flow (SCRUM-38) is reachable from a clean clone, and one left at
  Submitted so the coordinator review screen has something in it.
  These are *recreated on every run* — they are demo data, not user data.
- Three venues for the catalogue (SCRUM-59), one of them deactivated so the selectable
  list and the staff list visibly differ. Inserted only when missing, like the users.
"""

import uuid
from datetime import UTC, datetime, time, timedelta

from core.database import Session, SessionLocal
from core.security import hash_password
from domain.roles import Role
from models.event_request import EventRequest
from models.organisation import Organisation
from models.user import User
from models.venue import Venue
from repositories import event_requests as event_requests_repo
from repositories import users as users_repo
from services import event_requests as event_requests_service

_PRIMARY_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000010")

_SEED_ORGANISATIONS: tuple[tuple[uuid.UUID, str], ...] = (
    (_PRIMARY_ORG_ID, "Default Client Organisation"),
)

_SEED_USERS: list[tuple[str, str, list[Role], uuid.UUID]] = [
    ("organiser@example.com", "password123", [Role.ORGANISER], _PRIMARY_ORG_ID),
    ("coordinator@example.com", "password123", [Role.COORDINATOR], _PRIMARY_ORG_ID),
    # A second active coordinator, so a fresh `docker compose up` can demonstrate
    # round-robin assignment (SCRUM-34) rather than always assigning the same one.
    ("coordinator2@example.com", "password123", [Role.COORDINATOR], _PRIMARY_ORG_ID),
    ("venue-staff@example.com", "password123", [Role.VENUE_STAFF], _PRIMARY_ORG_ID),
    ("tech-support@example.com", "password123", [Role.TECH_SUPPORT], _PRIMARY_ORG_ID),
    ("attendee@example.com", "password123", [Role.ATTENDEE], _PRIMARY_ORG_ID),
    (
        "multi-role@example.com",
        "password123",
        [Role.ORGANISER, Role.COORDINATOR],
        _PRIMARY_ORG_ID,
    ),
]


# Fixed ids, so the samples can be found and replaced no matter what an organiser has
# renamed them to in the meantime. The rows are demo data: they are deleted and recreated
# on every seed run, which is also why the seed never writes a status directly — a fresh row
# is a draft by construction, and only domain/event_status.py may move it from there. The
# approved sample below gets there by calling the same services the UI calls, not by setting
# the column, so the seed cannot drift from the state machine.
_SAMPLE_IDS = (
    uuid.UUID("00000000-0000-4000-8000-000000000001"),
    uuid.UUID("00000000-0000-4000-8000-000000000002"),
    uuid.UUID("00000000-0000-4000-8000-000000000003"),
    uuid.UUID("00000000-0000-4000-8000-000000000004"),
)


def _sample_event_requests() -> list[tuple[uuid.UUID, dict[str, object]]]:
    start = (datetime.now(UTC) + timedelta(days=30)).replace(
        minute=0, second=0, microsecond=0
    )
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
    # Complete, and taken all the way to Approved by _approve_sample below, because
    # SCRUM-38 only lets a Coordinator book a venue for an APPROVED event. Without this a
    # clean clone cannot reach that flow at all.
    careers_fair: dict[str, object] = {
        "name": "Careers Fair",
        "purpose": "Connect final-year students with employers",
        "description": "Employer booths, on-the-day interviews and two panel sessions.",
        "start_at": start + timedelta(days=21),
        "end_at": start + timedelta(days=21, hours=6),
        "expected_attendance": 180,
        "venue_requirement": "Auditorium-type venue",
        "accessibility_requirement": "Step-free access",
        "equipment_requirement": "Projector-type requirement",
        "layout_requirement": "Theatre style",
        "registration_requirement": "Open registration, capped at 180",
    }
    # Submitted but not decided. Round-robin assignment (SCRUM-34) hands this one to the
    # *second* coordinator, because the careers fair above already took the first, so a
    # clean clone shows both halves of the review screen: one request you may decide and
    # one that is somebody else's to decide.
    alumni_dinner: dict[str, object] = {
        "name": "Alumni Dinner",
        "purpose": "Reconnect alumni with the faculty",
        "description": "Seated dinner with an after-dinner speaker.",
        "start_at": start + timedelta(days=35),
        "end_at": start + timedelta(days=35, hours=4),
        "expected_attendance": 150,
        "venue_requirement": "Auditorium-type venue",
        "accessibility_requirement": "Step-free access",
        "equipment_requirement": "Microphone-type requirement",
        "layout_requirement": "Banquet style",
        "registration_requirement": "Invitation only",
    }
    return [
        (_SAMPLE_IDS[0], orientation_day),
        (_SAMPLE_IDS[1], hackathon),
        (_SAMPLE_IDS[2], careers_fair),
        (_SAMPLE_IDS[3], alumni_dinner),
    ]


_SEED_VENUES: tuple[dict[str, object], ...] = (
    {
        # SCRUM-55 E2E: the venue the search spec filters for (Hall A in the tests).
        "name": "Hall A",
        "location": "Level 2, School of Computing",
        "maximum_capacity": 200,
        "facilities": ["Projector", "Hearing loop"],
        "supported_layouts": ["theatre", "classroom"],
        "accessibility_features": ["Step-free access"],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
        "is_active": True,
    },
    {
        "name": "Mochtar Riady Auditorium",
        "location": "Level 5, Administration Building",
        "maximum_capacity": 500,
        "facilities": ["Projector", "PA system", "Stage lighting"],
        "supported_layouts": ["theatre", "standing"],
        "accessibility_features": ["Step-free access", "Hearing loop"],
        "opens_at": time(8, 0),
        "closes_at": time(22, 0),
        "is_active": True,
    },
    {
        "name": "SCIS Seminar Room 2-1",
        "location": "Level 2, School of Computing and Information Systems",
        "maximum_capacity": 40,
        "facilities": ["Projector", "Whiteboard"],
        "supported_layouts": ["classroom", "boardroom", "u_shape"],
        "accessibility_features": ["Step-free access"],
        "opens_at": time(7, 30),
        "closes_at": time(21, 0),
        "is_active": True,
    },
    {
        # Deactivated on purpose: it should appear in the staff catalogue and not in the
        # selectable one, so SCRUM-59 AC3 and AC4 are both demonstrable from a fresh start.
        "name": "Old Sports Hall",
        "location": "Level 1, Campus Green",
        "maximum_capacity": 300,
        "facilities": ["PA system"],
        "supported_layouts": ["standing", "banquet"],
        "accessibility_features": [],
        "opens_at": time(9, 0),
        "closes_at": time(18, 0),
        "is_active": False,
    },
)


def _seed_venues(db: Session) -> None:
    """Insert missing catalogue venues; never touch existing rows."""
    for values in _SEED_VENUES:
        name = values["name"]
        if db.query(Venue).filter(Venue.name == name).first() is None:
            db.add(Venue(**values))


def _seed_organisations(db: Session) -> None:
    """Insert the client organisations used by local seed accounts."""
    for org_id, name in _SEED_ORGANISATIONS:
        if db.get(Organisation, org_id) is None:
            db.add(Organisation(id=org_id, name=name))


def _seed_users(db: Session) -> None:
    """Insert missing seed users; never touch existing rows."""
    for email, password, roles, organisation_id in _SEED_USERS:
        if users_repo.get_by_email(db, email) is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    roles=[role.value for role in roles],
                    organisation_id=organisation_id,
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
        event_requests_repo.add(
            db,
            EventRequest(
                id=sample_id,
                organiser_id=organiser.id,
                **fields,
            ),
        )
    db.flush()
    _approve_sample(db, organiser.id, _SAMPLE_IDS[2])
    event_requests_service.submit(db, _SAMPLE_IDS[3], organiser.id, datetime.now(UTC))


def _approve_sample(db: Session, organiser_id: uuid.UUID, request_id: uuid.UUID) -> None:
    """Drive one sample to Approved through the same services the UI calls.

    Submitting assigns a coordinator (SCRUM-34 round-robin), and only that coordinator may
    approve, so this also leaves a correctly assigned request behind rather than a row that
    happens to say "approved". Nothing here writes `status`.
    """
    now = datetime.now(UTC)
    submitted = event_requests_service.submit(db, request_id, organiser_id, now)
    if submitted.coordinator_id is None:
        return
    event_requests_service.approve(db, request_id, submitted.coordinator_id, now)


def main() -> None:
    db = SessionLocal()
    try:
        _seed_organisations(db)
        db.flush()
        _seed_users(db)
        db.flush()
        _seed_event_requests(db)
        _seed_venues(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
