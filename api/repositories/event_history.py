"""Read one event's source records for its history (SCRUM-88). Reads only, never writes.

Each function reads one source and returns the domain record the history reader for it
takes. People are LEFT joined to `users` for their email, as SCRUM-105 does (ADR-0047):
a missing user row must still show the entry, as an unknown user, never drop it.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from domain.event_change import ChangeRequestStatus
from domain.event_history import (
    AssignmentRecord,
    BookingRecord,
    BufferChangeRecord,
    ClarificationRecord,
    Person,
    ReplanCauseRecord,
    ReplanRecord,
    RequestRecord,
    RequirementChangeRecord,
    ReservationRecord,
)
from domain.event_replanning import ReplanCause
from models.equipment_requirement_change import EquipmentRequirementChange
from models.equipment_reservation import EquipmentReservation
from models.event_change_request import EventChangeRequest
from models.event_clarification import EventClarification
from models.event_request import EventRequest
from models.safety_review import SafetyReview
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_buffer_change import VenueBufferChange
from models.venue_closure_impact import VenueClosureImpact
from repositories import coordinator_assignments


def _person(user_id: uuid.UUID | None, email: str | None) -> Person | None:
    return None if user_id is None else Person(user_id, email)


def request_record(db: Session, event_request_id: uuid.UUID) -> RequestRecord:
    """The request's milestone columns with the owner, decider, confirmer and (SCRUM-120)
    canceller's emails. The request must exist: the history route's dependency has
    already loaded it."""
    owner, decider, confirmer = aliased(User), aliased(User), aliased(User)
    canceller = aliased(User)
    statement = (
        select(EventRequest, owner.email, decider.email, confirmer.email, canceller.email)
        .outerjoin(owner, EventRequest.organiser_id == owner.id)
        .outerjoin(decider, EventRequest.decided_by_id == decider.id)
        .outerjoin(confirmer, EventRequest.confirmed_by_id == confirmer.id)
        .outerjoin(canceller, EventRequest.cancelled_by_id == canceller.id)
        .where(EventRequest.id == event_request_id)
    )
    request, owner_email, decider_email, confirmer_email, canceller_email = (
        db.execute(statement).tuples().one()
    )
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
        cancelled_by=_person(request.cancelled_by_id, canceller_email),
        cancelled_at=request.cancelled_at,
        cancellation_reason=request.cancellation_reason,
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
    requester, decider, holder, canceller and adopter's emails."""
    requester, decider, holder = aliased(User), aliased(User), aliased(User)
    canceller, adopter = aliased(User), aliased(User)
    statement = (
        select(
            VenueBooking,
            Venue.name,
            requester.email,
            decider.email,
            holder.email,
            canceller.email,
            adopter.email,
        )
        .join(Venue, VenueBooking.venue_id == Venue.id)
        .outerjoin(requester, VenueBooking.requested_by_id == requester.id)
        .outerjoin(decider, VenueBooking.decided_by_id == decider.id)
        .outerjoin(holder, VenueBooking.held_by_id == holder.id)
        .outerjoin(canceller, VenueBooking.cancelled_by_id == canceller.id)
        .outerjoin(adopter, VenueBooking.adopted_by_id == adopter.id)
        .where(VenueBooking.event_request_id == event_request_id)
    )
    return [_booking_record(*row) for row in db.execute(statement).tuples()]


def _booking_record(
    booking: VenueBooking,
    venue_name: str,
    requester_email: str | None,
    decider_email: str | None,
    holder_email: str | None,
    canceller_email: str | None,
    adopter_email: str | None,
) -> BookingRecord:
    return BookingRecord(
        id=booking.id,
        status=booking.status,
        venue_name=venue_name,
        session_label=booking.session_label,
        start_at=booking.start_at,
        end_at=booking.end_at,
        requested_by=Person(booking.requested_by_id, requester_email),
        created_at=booking.created_at,
        decided_by=_person(booking.decided_by_id, decider_email),
        decided_at=booking.decided_at,
        decision_reason=booking.decision_reason,
        held_by=_person(booking.held_by_id, holder_email),
        held_at=booking.held_at,
        expires_at=booking.expires_at,
        cancelled_by=_person(booking.cancelled_by_id, canceller_email),
        cancelled_at=booking.cancelled_at,
        cancellation_reason=booking.cancellation_reason,
        replaces_booking_id=booking.replaces_booking_id,
        adopted_by=_person(booking.adopted_by_id, adopter_email),
        adopted_at=booking.adopted_at,
    )


def buffer_change_records(db: Session, booking_ids: list[uuid.UUID]) -> list[BufferChangeRecord]:
    """SCRUM-89's buffer changes that flagged any of these bookings, each with only the
    flagged ids among them. A change that flagged none of them did not affect the event as
    far as its record says, so it is not read (ADR-0064)."""
    if not booking_ids:
        return []
    changer = aliased(User)
    statement = (
        select(VenueBufferChange, Venue.name, changer.email)
        .join(Venue, VenueBufferChange.venue_id == Venue.id)
        .outerjoin(changer, VenueBufferChange.changed_by_id == changer.id)
        .where(VenueBufferChange.flagged_booking_ids.overlap(booking_ids))
    )
    ours = set(booking_ids)
    return [
        BufferChangeRecord(
            id=change.id,
            venue_name=venue_name,
            changed_by=Person(change.changed_by_id, email),
            changed_at=change.changed_at,
            old_setup_minutes=change.old_setup_minutes,
            old_turnaround_minutes=change.old_turnaround_minutes,
            new_setup_minutes=change.new_setup_minutes,
            new_turnaround_minutes=change.new_turnaround_minutes,
            affected_booking_ids=tuple(b for b in change.flagged_booking_ids if b in ours),
        )
        for change, venue_name, email in db.execute(statement).tuples()
    ]


def requirement_change_records(
    db: Session, event_request_id: uuid.UUID
) -> list[RequirementChangeRecord]:
    """SCRUM-43's change rows for the event, removed requirements included, with who."""
    changer = aliased(User)
    statement = (
        select(EquipmentRequirementChange, changer.email)
        .outerjoin(changer, EquipmentRequirementChange.changed_by_id == changer.id)
        .where(EquipmentRequirementChange.event_request_id == event_request_id)
    )
    return [
        RequirementChangeRecord(
            id=change.id,
            action=str(change.action),
            equipment_type=change.equipment_type,
            changed_by=Person(change.changed_by_id, email),
            changed_at=change.changed_at,
            old_quantity=change.old_quantity,
            new_quantity=change.new_quantity,
            old_technical_requirements=change.old_technical_requirements,
            new_technical_requirements=change.new_technical_requirements,
        )
        for change, email in db.execute(statement).tuples()
    ]


def reservation_records(db: Session, event_request_id: uuid.UUID) -> list[ReservationRecord]:
    """SCRUM-53's reservations for the event, released ones included, with who reserved
    and who released each."""
    reserver, releaser = aliased(User), aliased(User)
    statement = (
        select(EquipmentReservation, reserver.email, releaser.email)
        .outerjoin(reserver, EquipmentReservation.created_by_id == reserver.id)
        .outerjoin(releaser, EquipmentReservation.released_by_id == releaser.id)
        .where(EquipmentReservation.event_request_id == event_request_id)
    )
    return [
        ReservationRecord(
            id=reservation.id,
            equipment_type=reservation.equipment_type,
            quantity=reservation.quantity,
            reserved_by=Person(reservation.created_by_id, reserver_email),
            reserved_at=reservation.created_at,
            flagged_at=reservation.flagged_at,
            released_by=_person(reservation.released_by_id, releaser_email),
            released_at=reservation.released_at,
        )
        for reservation, reserver_email, releaser_email in db.execute(statement).tuples()
    ]


def replan_records(db: Session, event_request_id: uuid.UUID) -> list[ReplanRecord]:
    """SCRUM-130's invalidated approvals: each is one return to planning, with its cause."""
    statement = select(SafetyReview).where(
        SafetyReview.event_request_id == event_request_id,
        SafetyReview.invalidated_at.is_not(None),
    )
    return [
        ReplanRecord(review.id, review.invalidated_at, ReplanCause(review.invalidation_cause))
        for review in db.scalars(statement)
        # Drops nothing: the query and a check constraint set both together. It only
        # narrows the types for mypy.
        if review.invalidated_at is not None and review.invalidation_cause is not None
    ]


def replan_cause_records(
    db: Session, event_request_id: uuid.UUID, booking_ids: list[uuid.UUID]
) -> list[ReplanCauseRecord]:
    """The other actions that send an event back to planning, with who and when: approved
    change requests (SCRUM-47) and closures that hit one of these bookings (SCRUM-132).
    Venue changes are read from the bookings themselves. Neither has an entry of its own
    yet, so there is nothing to link to (ADR-0067)."""
    decider = aliased(User)
    changes = (
        select(EventChangeRequest, decider.email)
        .outerjoin(decider, EventChangeRequest.decided_by_id == decider.id)
        .where(
            EventChangeRequest.event_request_id == event_request_id,
            EventChangeRequest.status == ChangeRequestStatus.APPROVED,
        )
    )
    causes = [
        ReplanCauseRecord(
            ReplanCause.CHANGE_REQUEST, Person(change.decided_by_id, email), change.decided_at, None
        )
        for change, email in db.execute(changes).tuples()
        if change.decided_by_id is not None and change.decided_at is not None
    ]
    if not booking_ids:
        return causes
    recorder = aliased(User)
    closures = (
        select(VenueClosureImpact, recorder.email)
        .outerjoin(recorder, VenueClosureImpact.recorded_by_id == recorder.id)
        .where(VenueClosureImpact.affected_booking_ids.overlap(booking_ids))
    )
    return causes + [
        ReplanCauseRecord(
            ReplanCause.VENUE_CLOSURE,
            Person(impact.recorded_by_id, email),
            impact.recorded_at,
            None,
        )
        for impact, email in db.execute(closures).tuples()
    ]
