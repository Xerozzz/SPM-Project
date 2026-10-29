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
    ChangeItemRecord,
    ChangeRequestRecord,
    ClarificationRecord,
    ClosureImpactRecord,
    ClosureNoteRecord,
    HistoryAction,
    HoldExpiryChangeRecord,
    Person,
    ReplanCauseRecord,
    ReplanRecord,
    RequestRecord,
    RequirementChangeRecord,
    ReservationRecord,
    SafetyDecisionRecord,
)
from domain.event_replanning import ReplanCause
from domain.safety_review import SafetyDecision
from models.equipment_requirement_change import EquipmentRequirementChange
from models.equipment_reservation import EquipmentReservation
from models.event_change_request import EventChangeItem, EventChangeRequest
from models.event_clarification import EventClarification
from models.event_closure_note import EventClosureNote
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from models.safety_review import SafetyReview
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_buffer_change import VenueBufferChange
from models.venue_closure_impact import VenueClosureImpact
from models.venue_hold_expiry_change import VenueHoldExpiryChange
from repositories import coordinator_assignments


def _person(user_id: uuid.UUID | None, email: str | None) -> Person | None:
    return None if user_id is None else Person(user_id, email)


def request_record(db: Session, event_request_id: uuid.UUID) -> RequestRecord:
    """The request's milestone columns with the owner, decider, confirmer and (SCRUM-120)
    canceller and completer's emails. The request must exist: the history route's dependency has
    already loaded it."""
    owner, decider, confirmer = aliased(User), aliased(User), aliased(User)
    canceller, completer = aliased(User), aliased(User)
    statement = (
        select(
            EventRequest,
            owner.email,
            decider.email,
            confirmer.email,
            canceller.email,
            completer.email,
        )
        .outerjoin(owner, EventRequest.organiser_id == owner.id)
        .outerjoin(decider, EventRequest.decided_by_id == decider.id)
        .outerjoin(confirmer, EventRequest.confirmed_by_id == confirmer.id)
        .outerjoin(canceller, EventRequest.cancelled_by_id == canceller.id)
        .outerjoin(completer, EventRequest.completed_by_id == completer.id)
        .where(EventRequest.id == event_request_id)
    )
    request, owner_email, decider_email, confirmer_email, canceller_email, completer_email = (
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
        completed_by=_person(request.completed_by_id, completer_email),
        completed_at=request.completed_at,
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


def replan_cause_records(db: Session, event_request_id: uuid.UUID) -> list[ReplanCauseRecord]:
    """Approved change requests (SCRUM-47), as actions that send an event back to planning,
    with who and when. Each links to its decision entry (ADR-0068). Venue changes and
    closures are read from the bookings and closure impacts the history already has."""
    decider = aliased(User)
    changes = (
        select(EventChangeRequest, decider.email)
        .outerjoin(decider, EventChangeRequest.decided_by_id == decider.id)
        .where(
            EventChangeRequest.event_request_id == event_request_id,
            EventChangeRequest.status == ChangeRequestStatus.APPROVED,
        )
    )
    return [
        ReplanCauseRecord(
            ReplanCause.CHANGE_REQUEST,
            Person(change.decided_by_id, email),
            change.decided_at,
            f"{HistoryAction.CHANGE_DECIDED}:{change.id}",
        )
        for change, email in db.execute(changes).tuples()
        if change.decided_by_id is not None and change.decided_at is not None
    ]


def change_request_records(db: Session, event_request_id: uuid.UUID) -> list[ChangeRequestRecord]:
    """SCRUM-37/47's requests for the event, every status, with their items in order and
    the requester and decider's emails. Each item's subject is the session label or
    equipment type of the row it changes; removed lines keep their row (SCRUM-43)."""
    requester, decider = aliased(User), aliased(User)
    statement = (
        select(EventChangeRequest, requester.email, decider.email)
        .outerjoin(requester, EventChangeRequest.requested_by_id == requester.id)
        .outerjoin(decider, EventChangeRequest.decided_by_id == decider.id)
        .where(EventChangeRequest.event_request_id == event_request_id)
    )
    rows = db.execute(statement).tuples().all()
    items = db.scalars(
        select(EventChangeItem)
        .where(EventChangeItem.change_request_id.in_([change.id for change, _, _ in rows]))
        .order_by(EventChangeItem.position)
    ).all()
    subjects = _item_subjects(db, event_request_id)
    return [
        ChangeRequestRecord(
            id=change.id,
            requested_by=Person(change.requested_by_id, requester_email),
            created_at=change.created_at,
            reason=change.reason,
            status=change.status,
            decided_by=_person(change.decided_by_id, decider_email),
            decided_at=change.decided_at,
            decision_note=change.decision_note,
            items=tuple(
                ChangeItemRecord(
                    item.target,
                    item.field,
                    item.current_value,
                    item.proposed_value,
                    None if item.target_id is None else subjects.get(item.target_id),
                )
                for item in items
                if item.change_request_id == change.id
            ),
        )
        for change, requester_email, decider_email in rows
    ]


def _item_subjects(db: Session, event_request_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """The event's session labels and equipment types by row id, removed lines included."""
    sessions = db.execute(
        select(VenueBooking.id, VenueBooking.session_label).where(
            VenueBooking.event_request_id == event_request_id
        )
    ).tuples()
    lines = db.execute(
        select(EventEquipmentRequirement.id, EventEquipmentRequirement.equipment_type).where(
            EventEquipmentRequirement.event_request_id == event_request_id
        )
    ).tuples()
    return dict(sessions.all()) | dict(lines.all())


def closure_note_records(db: Session, event_request_id: uuid.UUID) -> list[ClosureNoteRecord]:
    """SCRUM-86's closure record versions for the event, with who recorded each."""
    recorder = aliased(User)
    statement = (
        select(EventClosureNote, recorder.email)
        .outerjoin(recorder, EventClosureNote.recorded_by_id == recorder.id)
        .where(EventClosureNote.event_request_id == event_request_id)
    )
    return [
        ClosureNoteRecord(
            id=note.id,
            version=note.version,
            actual_attendance=note.actual_attendance,
            notes=note.notes,
            recorded_by=Person(note.recorded_by_id, email),
            recorded_at=note.recorded_at,
        )
        for note, email in db.execute(statement).tuples()
    ]


def safety_decision_records(db: Session, event_request_id: uuid.UUID) -> list[SafetyDecisionRecord]:
    """SCRUM-79's decisions on the event, invalidated ones included, with the Officer's
    email. Whether the viewer may see them is the history's filter, not this read's."""
    officer = aliased(User)
    statement = (
        select(SafetyReview, officer.email)
        .outerjoin(officer, SafetyReview.decided_by_id == officer.id)
        .where(SafetyReview.event_request_id == event_request_id)
    )
    return [
        SafetyDecisionRecord(
            id=review.id,
            decision=SafetyDecision(review.decision),
            comment=review.comment,
            decided_by=Person(review.decided_by_id, email),
            decided_at=review.decided_at,
        )
        for review, email in db.execute(statement).tuples()
    ]


def closure_impact_records(db: Session, booking_ids: list[uuid.UUID]) -> list[ClosureImpactRecord]:
    """SCRUM-81's closure snapshots that affected any of these bookings, each with only
    the affected ids among them, as the buffer-change read does (ADR-0064). A closure that
    affected none of them has no link to the event, so it is not read."""
    if not booking_ids:
        return []
    recorder = aliased(User)
    statement = (
        select(VenueClosureImpact, Venue.name, recorder.email)
        .join(Venue, VenueClosureImpact.venue_id == Venue.id)
        .outerjoin(recorder, VenueClosureImpact.recorded_by_id == recorder.id)
        .where(VenueClosureImpact.affected_booking_ids.overlap(booking_ids))
    )
    ours = set(booking_ids)
    return [
        ClosureImpactRecord(
            id=impact.id,
            venue_name=venue_name,
            recorded_by=Person(impact.recorded_by_id, email),
            recorded_at=impact.recorded_at,
            starts_at=impact.starts_at,
            ends_at=impact.ends_at,
            reason=impact.reason,
            affected_booking_ids=tuple(b for b in impact.affected_booking_ids if b in ours),
        )
        for impact, venue_name, email in db.execute(statement).tuples()
    ]


def hold_expiry_change_records(
    db: Session, booking_ids: list[uuid.UUID]
) -> list[HoldExpiryChangeRecord]:
    """SCRUM-136's expiry changes to these bookings, with each hold's venue and session and
    the Venue Staff member's email."""
    if not booking_ids:
        return []
    changer = aliased(User)
    statement = (
        select(VenueHoldExpiryChange, VenueBooking, Venue.name, changer.email)
        .join(VenueBooking, VenueHoldExpiryChange.booking_id == VenueBooking.id)
        .join(Venue, VenueBooking.venue_id == Venue.id)
        .outerjoin(changer, VenueHoldExpiryChange.changed_by_id == changer.id)
        .where(VenueHoldExpiryChange.booking_id.in_(booking_ids))
    )
    return [
        HoldExpiryChangeRecord(
            id=change.id,
            venue_name=venue_name,
            session_label=booking.session_label,
            session_start_at=booking.start_at,
            session_end_at=booking.end_at,
            old_expires_at=change.old_expires_at,
            new_expires_at=change.new_expires_at,
            changed_by=Person(change.changed_by_id, email),
            changed_at=change.changed_at,
        )
        for change, booking, venue_name, email in db.execute(statement).tuples()
    ]
