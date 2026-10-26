"""Read one event's source records for its history (SCRUM-88). Reads only, never writes.

Each function reads one source and returns the domain record the history reader for it
takes. People are LEFT joined to `users` for their email, as SCRUM-105 does (ADR-0047):
a missing user row must still show the entry, as an unknown user, never drop it.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from domain.event_history import (
    AssignmentRecord,
    BookingRecord,
    ClarificationRecord,
    Person,
    RequestRecord,
)
from models.event_clarification import EventClarification
from models.event_request import EventRequest
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import coordinator_assignments


def _person(user_id: uuid.UUID | None, email: str | None) -> Person | None:
    return None if user_id is None else Person(user_id, email)


def request_record(db: Session, event_request_id: uuid.UUID) -> RequestRecord:
    """The request's milestone columns with the owner, decider and confirmer's emails.
    The request must exist: the history route's dependency has already loaded it."""
    owner, decider, confirmer = aliased(User), aliased(User), aliased(User)
    statement = (
        select(EventRequest, owner.email, decider.email, confirmer.email)
        .outerjoin(owner, EventRequest.organiser_id == owner.id)
        .outerjoin(decider, EventRequest.decided_by_id == decider.id)
        .outerjoin(confirmer, EventRequest.confirmed_by_id == confirmer.id)
        .where(EventRequest.id == event_request_id)
    )
    request, owner_email, decider_email, confirmer_email = db.execute(statement).tuples().one()
    return RequestRecord(
        id=request.id,
        owner=Person(request.organiser_id, owner_email),
        created_at=request.created_at,
        submitted_at=request.submitted_at,
        decided_by=_person(request.decided_by_id, decider_email),
        decided_at=request.decided_at,
        rejection_reason=request.rejection_reason,
        confirmed_by=_person(request.confirmed_by_id, confirmer_email),
        confirmed_at=request.confirmed_at,
    )


def assignment_records(db: Session, event_request_id: uuid.UUID) -> list[AssignmentRecord]:
    """SCRUM-97's history, read through SCRUM-105's query rather than a second one."""
    return [
        AssignmentRecord(
            id=entry.id,
            previous=_person(entry.previous_coordinator_id, previous_email),
            new=Person(entry.new_coordinator_id, new_email),
            acted_by=Person(entry.acted_by_id, acted_by_email),
            assigned_at=entry.assigned_at,
        )
        for entry, previous_email, new_email, acted_by_email in (
            coordinator_assignments.list_for_event_with_emails(db, event_request_id)
        )
    ]


def clarification_records(db: Session, event_request_id: uuid.UUID) -> list[ClarificationRecord]:
    """The event's clarification notes with each author's email."""
    author = aliased(User)
    statement = (
        select(EventClarification, author.email)
        .outerjoin(author, EventClarification.author_id == author.id)
        .where(EventClarification.event_request_id == event_request_id)
    )
    return [
        ClarificationRecord(
            id=note.id,
            author=Person(note.author_id, email),
            kind=note.kind,
            message=note.message,
            created_at=note.created_at,
        )
        for note, email in db.execute(statement).tuples()
    ]


def booking_records(db: Session, event_request_id: uuid.UUID) -> list[BookingRecord]:
    """The event's venue bookings, in every status, with the venue's name and the
    requester, decider and holder's emails."""
    requester, decider, holder = aliased(User), aliased(User), aliased(User)
    statement = (
        select(VenueBooking, Venue.name, requester.email, decider.email, holder.email)
        .join(Venue, VenueBooking.venue_id == Venue.id)
        .outerjoin(requester, VenueBooking.requested_by_id == requester.id)
        .outerjoin(decider, VenueBooking.decided_by_id == decider.id)
        .outerjoin(holder, VenueBooking.held_by_id == holder.id)
        .where(VenueBooking.event_request_id == event_request_id)
    )
    return [
        _booking_record(booking, venue_name, requester_email, decider_email, holder_email)
        for booking, venue_name, requester_email, decider_email, holder_email in (
            db.execute(statement).tuples()
        )
    ]


def _booking_record(
    booking: VenueBooking,
    venue_name: str,
    requester_email: str | None,
    decider_email: str | None,
    holder_email: str | None,
) -> BookingRecord:
    return BookingRecord(
        id=booking.id,
        status=booking.status,
        venue_name=venue_name,
        session_label=booking.session_label,
        requested_by=Person(booking.requested_by_id, requester_email),
        created_at=booking.created_at,
        decided_by=_person(booking.decided_by_id, decider_email),
        decided_at=booking.decided_at,
        decision_reason=booking.decision_reason,
        held_by=_person(booking.held_by_id, holder_email),
        held_at=booking.held_at,
        expires_at=booking.expires_at,
    )
