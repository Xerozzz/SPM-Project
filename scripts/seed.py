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
- Twelve manual end-to-end test scenarios, one per stage of an event's life, built in
  `seed_scenarios.py` and described in docs/manual-testing.md. Recreated on every run.
"""

import uuid
from datetime import UTC, datetime, time, timedelta

from core.database import Session, SessionLocal
from core.security import hash_password
from domain.roles import Role
from models.equipment import Equipment
from models.equipment_requirement_change import EquipmentRequirementChange
from models.equipment_reservation import EquipmentReservation
from models.event_cancellation_request import EventCancellationRequest
from models.event_change_request import EventChangeItem, EventChangeRequest
from models.event_clarification import EventClarification
from models.event_closure_note import EventClosureNote
from models.event_coordinator_assignment import EventCoordinatorAssignment
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_registration import EventRegistration, EventRegistrationHistory
from models.event_reminder import EventReminder
from models.event_request import EventRequest
from models.notification import Notification
from models.organisation import Organisation
from models.safety_review import SafetyReview
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
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
    # A second active coordinator, so assignment demos have more than one candidate.
    ("coordinator2@example.com", "password123", [Role.COORDINATOR], _PRIMARY_ORG_ID),
    # SCRUM-101: the Coordinator Lead triages the unassigned queue and assigns owners.
    ("coordinator-lead@example.com", "password123", [Role.COORDINATOR_LEAD], _PRIMARY_ORG_ID),
    ("venue-staff@example.com", "password123", [Role.VENUE_STAFF], _PRIMARY_ORG_ID),
    ("tech-support@example.com", "password123", [Role.TECH_SUPPORT], _PRIMARY_ORG_ID),
    # SCRUM-79: decides whether a plan has passed operational safety review.
    ("safety-officer@example.com", "password123", [Role.SAFETY_OFFICER], _PRIMARY_ORG_ID),
    ("attendee@example.com", "password123", [Role.ATTENDEE], _PRIMARY_ORG_ID),
    ("attendee2@example.com", "password123", [Role.ATTENDEE], _PRIMARY_ORG_ID),
    # Manual testing: enough attendees for one event to hold every registration status.
    ("attendee3@example.com", "password123", [Role.ATTENDEE], _PRIMARY_ORG_ID),
    ("attendee4@example.com", "password123", [Role.ATTENDEE], _PRIMARY_ORG_ID),
    ("attendee5@example.com", "password123", [Role.ATTENDEE], _PRIMARY_ORG_ID),
    (
        "multi-role@example.com",
        "password123",
        [Role.ORGANISER, Role.COORDINATOR],
        _PRIMARY_ORG_ID,
    ),
]

_SEED_EQUIPMENT: tuple[dict[str, object], ...] = (
    {
        "equipment_type": "Projector",
        "description": "Portable presentation projector",
        "total_quantity": 4,
        "location": "Media Store",
        "operational_status": "Operational",
    },
    {
        "equipment_type": "Microphone",
        "description": "Wireless presentation microphone",
        "total_quantity": 4,
        "location": "Audio Store",
        "operational_status": "Operational",
    },
)


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
    start = (datetime.now(UTC) + timedelta(days=30)).replace(minute=0, second=0, microsecond=0)
    orientation_day: dict[str, object] = {
        "name": "Orientation Day",
        "purpose": "Welcome new students to the faculty",
        "description": "Half-day programme with talks, a Q&A panel and a campus tour.",
        "start_at": start,
        "end_at": start + timedelta(hours=4),
        "expected_attendance": 200,
        "venue_requirement": "Mochtar Riady Auditorium",
        "accessibility_requirement": "Step-free access and a hearing loop",
        "equipment_requirement": "Projector",
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
        "venue_requirement": "Hall A",
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
        "venue_requirement": "Mochtar Riady Auditorium",
        "accessibility_requirement": "Step-free access",
        "equipment_requirement": "Projector",
        "layout_requirement": "Theatre style",
        "registration_requirement": "Open registration, capped at 180",
    }
    # Submitted but not decided. SCRUM-101 leaves submissions unassigned, so a clean
    # clone shows one in the Coordinator Lead unassigned queue.
    alumni_dinner: dict[str, object] = {
        "name": "Alumni Dinner",
        "purpose": "Reconnect alumni with the faculty",
        "description": "Seated dinner with an after-dinner speaker.",
        "start_at": start + timedelta(days=35),
        "end_at": start + timedelta(days=35, hours=4),
        "expected_attendance": 150,
        "venue_requirement": "Mochtar Riady Auditorium",
        "accessibility_requirement": "Step-free access",
        "equipment_requirement": "Microphone",
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


def _seed_equipment(db: Session) -> None:
    """Insert the catalogue entries used by the sample event requests when missing."""
    for values in _SEED_EQUIPMENT:
        if (
            db.query(Equipment)
            .filter(
                Equipment.equipment_type == values["equipment_type"],
                Equipment.location == values["location"],
            )
            .first()
            is None
        ):
            db.add(Equipment(**values))


def _seed_event_requests(db: Session) -> None:
    """Replace the sample requests so they are back in Draft, whatever happened to them."""
    organiser = users_repo.get_by_email(db, "organiser@example.com")
    if organiser is None:
        return
    for sample_id, fields in _sample_event_requests():
        existing = event_requests_repo.get(db, sample_id)
        if existing is not None:
            _delete_dependents(db, sample_id)
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


# Everything that points at an event request. None of these foreign keys cascade, and
# nothing in the application deletes an event request — only this seed does, to put the
# samples back in Draft. So the seed is what has to clear up after itself.
#
# This is why a second `docker compose up` against an existing volume used to kill the
# API on startup: approving a sample now creates an equipment requirement (SCRUM-43),
# and deleting the sample on the next run hit that row's foreign key. CI never saw it
# because a fresh runner always starts from an empty volume.
_DEPENDENTS = (
    EquipmentRequirementChange,
    # SCRUM-37 and SCRUM-47. Its own children go first, in `_delete_dependents`, because
    # they hang off the change request rather than off the event.
    EventChangeRequest,
    # Before the requirements themselves: a reservation points at the requirement row,
    # so deleting that row first is refused (SCRUM-53). Order in this tuple is the
    # delete order, children first.
    EquipmentReservation,
    EventEquipmentRequirement,
    EventClarification,
    # SCRUM-85: a reminder schedule points at the event it is for.
    EventReminder,
    # SCRUM-86: closure notes of a completed event.
    EventClosureNote,
    # SCRUM-115: an Organiser's cancellation requests.
    EventCancellationRequest,
    EventCoordinatorAssignment,
    Notification,
    # SCRUM-42. History points at a registration rather than the event, so it is
    # cleared explicitly in `_delete_dependents` before this event-scoped row.
    EventRegistration,
    # SCRUM-79, and the same trap a third time: a Safety Officer's decision points at the
    # event it judged, so once one exists against a sample the next seed run cannot put
    # that sample back in Draft. CI starts from an empty volume and never sees it; the
    # team's second `docker compose up` does, and the API dies on startup.
    SafetyReview,
    VenueBooking,
)


def _delete_dependents(db: Session, request_id: uuid.UUID) -> None:
    """Clear the rows that would otherwise refuse the delete, children first."""
    # The one grandchild: a change item points at its change request, not at the event,
    # so the loop below cannot reach it and deleting the request would be refused.
    db.query(EventChangeItem).filter(
        EventChangeItem.change_request_id.in_(
            db.query(EventChangeRequest.id).filter(
                EventChangeRequest.event_request_id == request_id
            )
        )
    ).delete(synchronize_session=False)
    # SCRUM-42: registration history hangs off the registration, not directly off the
    # event, so clear it before the event-scoped registration row below.
    db.query(EventRegistrationHistory).filter(
        EventRegistrationHistory.registration_id.in_(
            db.query(EventRegistration.id).filter(EventRegistration.event_request_id == request_id)
        )
    ).delete(synchronize_session=False)
    for model in _DEPENDENTS:
        db.query(model).filter(model.event_request_id == request_id).delete(
            synchronize_session=False
        )
    db.flush()


def _approve_sample(db: Session, organiser_id: uuid.UUID, request_id: uuid.UUID) -> None:
    """Drive one sample to Approved through the same services the UI calls.

    SCRUM-101 leaves submissions unassigned, so the seed assigns the first active
    coordinator directly (test/demo setup, not a user path) before approving — only
    the assigned coordinator may approve. Nothing here writes `status`.
    """
    now = datetime.now(UTC)
    submitted = event_requests_service.submit(db, request_id, organiser_id, now)
    coordinators = users_repo.list_active_coordinators(db)
    if not coordinators:
        return
    submitted.coordinator_id = coordinators[0].id
    submitted.assigned_at = now
    db.flush()
    event_requests_service.approve(db, request_id, submitted.coordinator_id, now)


def _seed_scenarios(db: Session) -> None:
    """The manual testing scenarios. Imported here rather than at the top, because the
    seed's own unit test loads this file by path, where `scripts/` is not importable."""
    from seed_scenarios import seed

    seed(db, _delete_dependents)


def main() -> None:
    db = SessionLocal()
    try:
        _seed_organisations(db)
        db.flush()
        _seed_users(db)
        db.flush()
        _seed_equipment(db)
        db.flush()
        _seed_venues(db)
        db.flush()
        _seed_event_requests(db)
        db.commit()
        _seed_scenarios(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
