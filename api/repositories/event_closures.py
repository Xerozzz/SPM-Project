"""Event closure persistence (SCRUM-86)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from models.equipment_requirement_change import EquipmentRequirementChange
from models.equipment_reservation import EquipmentReservation
from models.event_closure_note import EventClosureNote
from models.event_request import EventRequest
from models.safety_review import SafetyReview
from models.venue_booking import VenueBooking


def notes_for_event(db: Session, event_request_id: uuid.UUID) -> list[EventClosureNote]:
    """Every version of the closure record, oldest first."""
    statement = (
        select(EventClosureNote)
        .where(EventClosureNote.event_request_id == event_request_id)
        .order_by(EventClosureNote.version)
    )
    return list(db.scalars(statement))


def add_note(db: Session, note: EventClosureNote) -> EventClosureNote:
    """Stage one version and flush it, without committing."""
    db.add(note)
    db.flush()
    return note


def acted_on_event(db: Session, event_request_id: uuid.UUID) -> set[uuid.UUID]:
    """AC4: everyone recorded as acting on this event's arrangements or safety review.

    Venue decisions and holds, equipment line changes and reservations, and safety
    decisions. The caller still checks the viewer holds a staff role.
    """
    columns = (
        (VenueBooking.decided_by_id, VenueBooking.event_request_id),
        (VenueBooking.held_by_id, VenueBooking.event_request_id),
        (EquipmentRequirementChange.changed_by_id, EquipmentRequirementChange.event_request_id),
        (EquipmentReservation.created_by_id, EquipmentReservation.event_request_id),
        (SafetyReview.decided_by_id, SafetyReview.event_request_id),
    )
    actors: set[uuid.UUID] = set()
    for actor, event in columns:
        statement = select(actor).where(event == event_request_id).distinct()
        actors.update(row for row in db.scalars(statement) if row is not None)
    return actors


def list_completed_for_coordinator(db: Session, coordinator_id: uuid.UUID) -> list[EventRequest]:
    """Completed events whose current assigned Coordinator may correct the record."""
    statement = (
        select(EventRequest)
        .where(
            EventRequest.status == EventStatus.COMPLETED,
            EventRequest.coordinator_id == coordinator_id,
        )
        .order_by(EventRequest.start_at.desc(), EventRequest.id.asc())
    )
    return list(db.scalars(statement))
