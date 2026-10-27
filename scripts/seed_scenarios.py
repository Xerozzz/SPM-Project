"""Manual end-to-end test scenarios, one event per stage of the lifecycle.

`seed.py` calls `seed(db, delete_dependents)` after the users, venues and samples. Each
scenario is a fixed-id event owned by organiser@example.com and assigned to
coordinator@example.com, so a tester signs in as those two (and the staff accounts) and
finds every feature with something already in it. The scenarios are rebuilt on every run,
like the samples, so a tester can wreck them freely and get them back with a re-seed.

Every state is reached through the same services the UI calls. Nothing writes a status
column. The one exception is moving two Confirmed events into the past, so "complete an
event that has ended" can be tried today. Those dates are shifted directly after
confirmation, because no screen lets anyone set an event in the past.

The events use their own venues ("Test Hall East", "Test Hall West", "Test Studio") and
dates a few weeks out, so they never take a slot the automated E2E specs book.

See docs/manual-testing.md for which account tests what.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta

from core.database import Session
from domain.change_decision import Decision
from domain.equipment_requirement import RequirementReview
from domain.event_change import Proposal
from domain.event_clarification import ClarificationKind
from domain.registration import RegistrationStatus
from domain.safety_review import SafetyDecision, fingerprint
from domain.venue_unavailability import VenueUnavailabilityFields
from models.equipment_reservation import EquipmentReservation
from models.event_request import EventRequest
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_closure_impact import VenueClosureImpact
from models.venue_unavailability import VenueUnavailability
from repositories import equipment_requirements as requirement_repo
from repositories import event_requests as event_repo
from repositories import users as users_repo
from services import (
    equipment_requirements,
    equipment_reservations,
    event_cancellations,
    event_change_requests,
    event_clarifications,
    event_completions,
    event_confirmations,
    event_registrations,
    event_reminders,
    event_requests,
    registration_intake,
    safety_reviews,
    venue_booking_decisions,
    venue_bookings,
    venue_unavailabilities,
)

# Fixed ids, so a re-run finds and replaces exactly these events.
_IDS = {n: uuid.UUID(f"00000000-0000-4000-8000-0000000001{n:02d}") for n in range(1, 13)}

# Venues only these scenarios book, so their holds never block an automated spec.
_VENUES: tuple[dict[str, object], ...] = (
    {
        "name": "Test Hall East",
        "location": "Manual testing, east wing",
        "maximum_capacity": 250,
        "facilities": ["Projector", "PA system"],
        "supported_layouts": ["theatre", "classroom"],
        "accessibility_features": ["Step-free access"],
        "opens_at": time(0, 0),
        "closes_at": time(23, 59),
        "is_active": True,
    },
    {
        "name": "Test Hall West",
        "location": "Manual testing, west wing",
        "maximum_capacity": 250,
        "facilities": ["Projector"],
        "supported_layouts": ["theatre", "banquet"],
        "accessibility_features": ["Step-free access"],
        "opens_at": time(0, 0),
        "closes_at": time(23, 59),
        "is_active": True,
    },
    {
        "name": "Test Studio",
        "location": "Manual testing, level 3",
        "maximum_capacity": 60,
        "facilities": ["Projector", "Whiteboard"],
        "supported_layouts": ["classroom", "boardroom"],
        "accessibility_features": ["Step-free access", "Hearing loop"],
        "opens_at": time(0, 0),
        "closes_at": time(23, 59),
        "is_active": True,
    },
)


DeleteDependents = Callable[[Session, uuid.UUID], None]
Window = tuple[datetime, datetime]


class _People:
    """The seeded accounts each scenario acts as."""

    def __init__(self, db: Session) -> None:
        def user(email: str) -> User:
            found = users_repo.get_by_email(db, email)
            assert found is not None, f"{email} is seeded before the scenarios"
            return found

        self.organiser = user("organiser@example.com")
        self.coordinator = user("coordinator@example.com")
        self.lead = user("coordinator-lead@example.com")
        self.venue_staff = user("venue-staff@example.com")
        self.tech = user("tech-support@example.com")
        self.officer = user("safety-officer@example.com")
        self.attendees = [
            user(email)
            for email in (
                "attendee@example.com",
                "attendee2@example.com",
                "attendee3@example.com",
                "attendee4@example.com",
                "attendee5@example.com",
            )
        ]


def seed(db: Session, delete_dependents: DeleteDependents) -> None:
    """Rebuild every scenario from scratch."""
    venues = _ensure_venues(db)
    _clear(db, venues, delete_dependents)
    people = _People(db)
    now = datetime.now(UTC)
    # 10:00 to 14:00 Singapore time, a few weeks out, one day per scenario.
    base = datetime(now.year, now.month, now.day, 2, tzinfo=UTC) + timedelta(days=21)
    east, west, studio = venues

    def day(n: int) -> tuple[datetime, datetime]:
        start = base + timedelta(days=n)
        return start, start + timedelta(hours=4)

    _rejected(db, people, day(1), now)
    _awaiting_review(db, people, day(2), now)
    _venue_request_pending(db, people, east, day(3), now)
    _ready_for_safety_review(db, people, west, day(4), now)
    _ready_to_confirm(db, people, studio, day(5), now)
    _confirmed_with_registrations(db, people, east, day(6), now)
    _cancellation_requested(db, people, west, day(7), now)
    _ended_ready_to_complete(db, people, studio, day(8), now)
    _completed(db, people, east, day(9), now)
    _cancelled(db, people, west, day(10), now)
    _venue_closed_over_hold(db, people, studio, day(11), now)
    _rejected_venue_request(db, people, east, day(12), now)
    db.commit()


# --------------------------------------------------------------------------- set-up


def _ensure_venues(db: Session) -> list[Venue]:
    """Create the test venues, or put back anything a tester changed on them, so a
    restart really is a full reset. Buffers go back to none, the column default."""
    found: list[Venue] = []
    for values in _VENUES:
        venue = db.query(Venue).filter(Venue.name == values["name"]).first()
        if venue is None:
            venue = Venue(**values)
            db.add(venue)
        else:
            for key, value in values.items():
                setattr(venue, key, value)
            venue.setup_minutes = 0
            venue.turnaround_minutes = 0
        db.flush()
        found.append(venue)
    return found


def _clear(db: Session, venues: list[Venue], delete_dependents: DeleteDependents) -> None:
    """Remove the scenarios and the closures on the test venues from the last run."""
    venue_ids = [venue.id for venue in venues]
    db.query(VenueClosureImpact).filter(VenueClosureImpact.venue_id.in_(venue_ids)).delete(
        synchronize_session=False
    )
    db.query(VenueUnavailability).filter(VenueUnavailability.venue_id.in_(venue_ids)).delete(
        synchronize_session=False
    )
    for event_id in _IDS.values():
        existing = event_repo.get(db, event_id)
        if existing is not None:
            delete_dependents(db, event_id)
            event_repo.delete(db, existing)
    db.flush()


def _event(
    db: Session,
    people: _People,
    number: int,
    name: str,
    window: Window,
    *,
    equipment: str | None = "Projector",
    registration: str | None = "Open registration, capped at 120",
) -> EventRequest:
    start, end = window
    event = EventRequest(
        id=_IDS[number],
        organiser_id=people.organiser.id,
        name=name,
        purpose="Manual end-to-end testing",
        description=f"Seeded for manual testing. See docs/manual-testing.md, scenario {number}.",
        start_at=start,
        end_at=end,
        expected_attendance=120,
        venue_requirement="Test Hall East",
        accessibility_requirement="Step-free access",
        equipment_requirement=equipment,
        layout_requirement="Theatre style",
        registration_requirement=registration,
    )
    event_repo.add(db, event)
    db.flush()
    return event


def _submitted(db: Session, people: _People, event: EventRequest, now: datetime) -> None:
    """Submit and have the Lead assign it to coordinator@ (SCRUM-46, SCRUM-101)."""
    event_requests.submit(db, event.id, people.organiser.id, now)
    event_requests.assign_coordinator(
        db, event.id, people.coordinator.id, now, acted_by_id=people.lead.id
    )


def _approved(db: Session, people: _People, event: EventRequest, now: datetime) -> None:
    _submitted(db, people, event, now)
    event_requests.approve(db, event.id, people.coordinator.id, now)


def _held(
    db: Session,
    people: _People,
    event: EventRequest,
    venue: Venue,
    now: datetime,
    label: str = "Main session",
) -> VenueBooking:
    """Request the venue and have Venue Staff approve it, which places the hold."""
    assert event.start_at is not None and event.end_at is not None
    booking, _ = venue_bookings.submit(
        db, event, venue.id, now, label, event.start_at, event.end_at, None
    )
    return venue_bookings.approve(
        db, booking.id, people.venue_staff.id, now, event.start_at - timedelta(days=1)
    )


def _equipment_reserved(db: Session, people: _People, event: EventRequest, now: datetime) -> None:
    """Tech Support reviews each requirement as available and reserves it (SCRUM-53)."""
    for requirement in requirement_repo.list_for_event(db, event.id):
        equipment_requirements.review(db, requirement.id, RequirementReview.AVAILABLE, now)
        equipment_reservations.reserve(db, event.id, requirement.id, None, people.tech.id, now)


def _safety_approved(db: Session, people: _People, event: EventRequest, now: datetime) -> None:
    plan = safety_reviews.plan_of(db, event, now)
    safety_reviews.record(
        db,
        event,
        SafetyDecision.APPROVE,
        "Exits, capacity and step-free access all check out.",
        fingerprint(plan),
        people.officer.id,
        now,
    )


def _confirmed(
    db: Session,
    people: _People,
    number: int,
    name: str,
    venue: Venue,
    window: Window,
    now: datetime,
) -> tuple[EventRequest, VenueBooking]:
    event = _event(db, people, number, name, window)
    _approved(db, people, event, now)
    booking = _held(db, people, event, venue, now)
    _equipment_reserved(db, people, event, now)
    _safety_approved(db, people, event, now)
    event_confirmations.confirm(db, event, people.coordinator.id, now)
    return event, booking


def _register(
    db: Session, event: EventRequest, attendee: User, name: str, now: datetime
) -> uuid.UUID:
    registration = event_registrations.submit(
        db, event.id, attendee.id, name, 21, "+65 8123 4567", None, now
    )
    return registration.id


def _into_the_past(db: Session, event: EventRequest, booking: VenueBooking, now: datetime) -> None:
    """Move a Confirmed event and its booking to yesterday, so it has ended.

    The only direct write in the scenarios: no screen can put an event in the past, and
    completing one needs it to have ended (SCRUM-86).
    """
    shift = (now - timedelta(days=1)) - (event.start_at or now)
    event.start_at = (event.start_at or now) + shift
    event.end_at = (event.end_at or now) + shift
    for row in (booking,):
        row.start_at += shift
        row.end_at += shift
        row.effective_start_at += shift
        row.effective_end_at += shift
    for reservation in db.query(EquipmentReservation).filter(
        EquipmentReservation.event_request_id == event.id
    ):
        reservation.starts_at += shift
        reservation.ends_at += shift
    db.flush()


# --------------------------------------------------------------------------- scenarios


def _rejected(db: Session, people: _People, window: Window, now: datetime) -> None:
    """1. Rejected with a reason. The Organiser edits it and submits again (SCRUM-31)."""
    event = _event(db, people, 1, "Test 01: Rejected, edit and resubmit", window)
    _submitted(db, people, event, now)
    event_requests.reject(
        db,
        event.id,
        people.coordinator.id,
        "Expected attendance is too high for the venue asked for. Please lower it.",
        now,
    )


def _awaiting_review(db: Session, people: _People, window: Window, now: datetime) -> None:
    """2. Submitted and assigned, with an internal note. Approve, reject, reassign
    (SCRUM-31, SCRUM-102, SCRUM-106)."""
    event = _event(db, people, 2, "Test 02: Awaiting review", window)
    _submitted(db, people, event, now)
    event_clarifications.create_message(
        db,
        event.id,
        people.coordinator.id,
        ClarificationKind.REQUEST,
        "Check the expected attendance against last year's numbers.",
        now,
    )


def _venue_request_pending(
    db: Session, people: _People, venue: Venue, window: Window, now: datetime
) -> None:
    """3. Planning. A venue request waits for Venue Staff and the Projector waits for
    Tech Support (SCRUM-40, SCRUM-110, SCRUM-43, SCRUM-124)."""
    event = _event(db, people, 3, "Test 03: Venue request waiting", window)
    _approved(db, people, event, now)
    assert event.start_at is not None and event.end_at is not None
    venue_bookings.submit(
        db, event, venue.id, now, "Main session", event.start_at, event.end_at, None
    )


def _ready_for_safety_review(
    db: Session, people: _People, venue: Venue, window: Window, now: datetime
) -> None:
    """4. Planning, venue held and equipment reserved. The Safety Officer reviews it
    (SCRUM-79, SCRUM-50)."""
    event = _event(db, people, 4, "Test 04: Ready for safety review", window)
    _approved(db, people, event, now)
    _held(db, people, event, venue, now)
    _equipment_reserved(db, people, event, now)
    # SCRUM-50: tell the Safety Officers, as the readiness check on screen would.
    event_confirmations.announce_review_due(db, event, now)
    db.commit()


def _ready_to_confirm(
    db: Session, people: _People, venue: Venue, window: Window, now: datetime
) -> None:
    """5. Everything in order. The Coordinator confirms it (SCRUM-80), and can set
    reminders first (SCRUM-85)."""
    event = _event(db, people, 5, "Test 05: Ready to confirm", window)
    _approved(db, people, event, now)
    _held(db, people, event, venue, now)
    _equipment_reserved(db, people, event, now)
    _safety_approved(db, people, event, now)


def _confirmed_with_registrations(
    db: Session, people: _People, venue: Venue, window: Window, now: datetime
) -> None:
    """6. Confirmed and open for registration, one registration in each status, a
    change waiting for a decision and reminders set (SCRUM-42, 113, 114, 128, 134, 37,
    47, 85). attendee@ is not registered, so they can register themselves."""
    event, _ = _confirmed(
        db, people, 6, "Test 06: Confirmed, registrations open", venue, window, now
    )
    # A closing deadline, so the Organiser can also try extending it (SCRUM-113).
    assert event.start_at is not None
    registration_intake.open_intake(db, event.id, event.start_at - timedelta(days=3), now)
    db.commit()
    _, accepted, waitlisted, withdrawn, pending = people.attendees
    _register(db, event, pending, "Eve Pending", now)
    accepted_id = _register(db, event, accepted, "Bea Accepted", now)
    waitlisted_id = _register(db, event, waitlisted, "Cal Waitlisted", now)
    _register(db, event, withdrawn, "Dee Withdrawn", now)
    later = now + timedelta(seconds=1)
    event_registrations.decide(
        db,
        event.id,
        accepted_id,
        people.organiser.id,
        RegistrationStatus.PENDING,
        RegistrationStatus.ACCEPTED,
        None,
        later,
    )
    event_registrations.decide(
        db,
        event.id,
        waitlisted_id,
        people.organiser.id,
        RegistrationStatus.PENDING,
        RegistrationStatus.WAITLISTED,
        "Room is close to full",
        later,
    )
    event_registrations.withdraw(db, event.id, withdrawn.id, later)
    event_change_requests.submit(
        db,
        event.id,
        people.organiser.id,
        Proposal(
            reason="More students signed up than expected.",
            event={"expected_attendance": 150},
        ),
        uuid.uuid4(),
        later,
    )
    event_reminders.configure(db, event, [10080, 1440], people.coordinator.id, later)


def _cancellation_requested(
    db: Session, people: _People, venue: Venue, window: Window, now: datetime
) -> None:
    """7. Confirmed, and the Organiser has asked to cancel it. The Coordinator applies
    or declines the request (SCRUM-115)."""
    event, _ = _confirmed(db, people, 7, "Test 07: Cancellation requested", venue, window, now)
    event_cancellations.request_cancellation(
        db, event.id, people.organiser.id, "The guest speaker can no longer come.", now
    )


def _ended_ready_to_complete(
    db: Session, people: _People, venue: Venue, window: Window, now: datetime
) -> None:
    """8. Confirmed and ended yesterday. The Coordinator completes it (SCRUM-86)."""
    event, booking = _confirmed(
        db, people, 8, "Test 08: Ended, ready to complete", venue, window, now
    )
    _into_the_past(db, event, booking, now)
    db.commit()


def _completed(db: Session, people: _People, venue: Venue, window: Window, now: datetime) -> None:
    """9. Completed with a closure record. Read it, correct it, see the history
    (SCRUM-86, SCRUM-88)."""
    event, booking = _confirmed(db, people, 9, "Test 09: Completed", venue, window, now)
    _into_the_past(db, event, booking, now)
    db.commit()
    event_completions.complete(
        db, event.id, people.coordinator.id, 104, "Ran 20 minutes late. No other issues.", now
    )


def _cancelled(db: Session, people: _People, venue: Venue, window: Window, now: datetime) -> None:
    """10. Cancelled after registrations came in. Everything is released and everyone
    who took part is told (SCRUM-115, SCRUM-135)."""
    event, _ = _confirmed(db, people, 10, "Test 10: Cancelled", venue, window, now)
    registration_intake.open_intake(db, event.id, None, now)
    db.commit()
    _register(db, event, people.attendees[1], "Bea Accepted", now)
    event_cancellations.cancel(
        db, event.id, people.coordinator.id, "Storm warning for that day.", None, now
    )


def _venue_closed_over_hold(
    db: Session, people: _People, venue: Venue, window: Window, now: datetime
) -> None:
    """11. Planning with a held venue that Venue Staff then closed. The Coordinator sees
    the impact and books a replacement (SCRUM-81, SCRUM-116, SCRUM-133)."""
    event = _event(db, people, 11, "Test 11: Venue closed over a hold", window)
    _approved(db, people, event, now)
    _held(db, people, event, venue, now)
    assert event.start_at is not None and event.end_at is not None
    venue_unavailabilities.create(
        db,
        venue.id,
        VenueUnavailabilityFields(
            starts_at=event.start_at - timedelta(hours=1),
            ends_at=event.end_at + timedelta(hours=1),
            reason="Air conditioning repairs",
        ),
        people.venue_staff.id,
        now,
    )


def _rejected_venue_request(
    db: Session, people: _People, venue: Venue, window: Window, now: datetime
) -> None:
    """12. Planning, the first venue request was rejected and a change was approved.
    Search for another venue and see the decided change (SCRUM-55, SCRUM-75, SCRUM-47)."""
    event = _event(db, people, 12, "Test 12: Venue rejected, find another", window)
    _approved(db, people, event, now)
    assert event.start_at is not None and event.end_at is not None
    booking, _ = venue_bookings.submit(
        db, event, venue.id, now, "Main session", event.start_at, event.end_at, None
    )
    venue_booking_decisions.reject(
        db, booking.id, people.venue_staff.id, "Booked for exams that week.", now
    )
    change, _ = event_change_requests.submit(
        db,
        event.id,
        people.organiser.id,
        Proposal(reason="Shorter programme.", event={"expected_attendance": 90}),
        uuid.uuid4(),
        now,
    )
    event_change_requests.decide(
        db, event.id, change.id, people.coordinator.id, Decision.APPROVE, "Fine by me.", now
    )
