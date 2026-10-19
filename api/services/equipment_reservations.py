"""Technical Support Staff reserve equipment for an event (SCRUM-53). ADR-0038.

The planning rule is SCRUM-44's `review_refusal`, and stock is SCRUM-52's
`count_in_service`, so a reservation is refused in exactly the cases a review or an
availability check would be. What is new is the decision of how many to take, which is in
`domain.equipment_reservation`.

Nothing here releases a reservation when an event changes; that is Event Change
Management's work.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from domain.equipment_availability import StockEntry, count_in_service
from domain.equipment_requirement import ReviewRefusal, review_refusal
from domain.equipment_reservation import (
    ReservationRefusal,
    ReservationState,
    free_quantity,
    outstanding_quantity,
    quantity_to_reserve,
    reservation_state,
)
from models.equipment_reservation import EquipmentReservation
from repositories import equipment as catalogue_repo
from repositories import equipment_requirements as requirement_repo
from repositories import equipment_reservations as repo
from repositories import event_requests as event_request_repo
from services.equipment_requirements import RequirementNotFoundError, ReviewNotAllowedError


class EventWindowMissingError(Exception):
    """The event has no start or end, so there is no period to reserve over."""


class ReservationRefusedError(Exception):
    """Nothing was reserved, with the reason."""

    def __init__(self, refusal: ReservationRefusal) -> None:
        super().__init__(refusal.value)
        self.refusal = refusal


@dataclass(frozen=True)
class ReservationOutcome:
    """AC7: what was reserved, and where the requirement now stands."""

    requirement_id: uuid.UUID
    event_request_id: uuid.UUID
    equipment_type: str
    reserved_now: int
    total_reserved: int
    outstanding: int
    state: ReservationState
    event_start_at: datetime
    event_end_at: datetime


def reserve(
    db: Session,
    event_request_id: uuid.UUID,
    requirement_id: uuid.UUID,
    asked: int | None,
    actor_id: uuid.UUID,
    now: datetime,
) -> ReservationOutcome:
    """AC1 to AC5: reserve some or all of what a requirement still needs."""
    requirement = requirement_repo.get(db, requirement_id)
    # Another event's requirement is reported as missing, as `_live_requirement` does.
    if requirement is None or requirement.event_request_id != event_request_id:
        raise RequirementNotFoundError
    event = event_request_repo.get(db, event_request_id)
    # The foreign key guarantees the event exists; this only narrows the type for mypy.
    assert event is not None
    refusal = review_refusal(event.status, removed=requirement.removed_at is not None)
    if refusal is ReviewRefusal.REQUIREMENT_REMOVED:
        raise RequirementNotFoundError
    if refusal is ReviewRefusal.EVENT_NOT_IN_PLANNING:
        raise ReviewNotAllowedError
    if event.start_at is None or event.end_at is None:
        raise EventWindowMissingError

    # Locked first, so everything counted below stays true until the commit (ADR-0038).
    entries = catalogue_repo.lock_entries_of_type(db, requirement.equipment_type)
    stock = count_in_service(
        StockEntry(e.total_quantity, e.operational_status, e.is_active) for e in entries
    )
    reserved_elsewhere = catalogue_repo.reserved_quantity(
        db, requirement.equipment_type, event.start_at, event.end_at, excluding_event_id=event.id
    )
    held_here = repo.held_by_event(db, event.id, requirement.equipment_type)
    already = repo.held_by_requirement(db, requirement.id)
    decided = quantity_to_reserve(
        asked,
        outstanding_quantity(requirement.quantity, already),
        free_quantity(stock, reserved_elsewhere, held_here),
    )
    if isinstance(decided, ReservationRefusal):
        raise ReservationRefusedError(decided)

    repo.add(
        db,
        EquipmentReservation(
            requirement_id=requirement.id,
            event_request_id=event.id,
            equipment_type=requirement.equipment_type,
            quantity=decided,
            starts_at=event.start_at,
            ends_at=event.end_at,
            created_by_id=actor_id,
            created_at=now,
        ),
    )
    total = already + decided
    return ReservationOutcome(
        requirement_id=requirement.id,
        event_request_id=event.id,
        equipment_type=requirement.equipment_type,
        reserved_now=decided,
        total_reserved=total,
        outstanding=outstanding_quantity(requirement.quantity, total),
        state=reservation_state(requirement.quantity, total),
        event_start_at=event.start_at,
        event_end_at=event.end_at,
    )
