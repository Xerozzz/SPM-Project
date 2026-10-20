"""Venue Staff booking decision contracts (SCRUM-40, SCRUM-75)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from domain.booking_conflict import (
    BookingConflictError,
    ConflictingBookingError,
    VenueUnavailableError,
)
from domain.venue_booking import BookingStatus
from domain.venue_booking_decision import MAX_REASON_LENGTH
from domain.venue_buffer import VenueBuffers, effective_interval
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking


class VenueBookingReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MAX_REASON_LENGTH)


class VenueBookingHold(BaseModel):
    """SCRUM-83 AC1: when a tentative hold stops holding the venue."""

    model_config = ConfigDict(extra="forbid")

    # AwareDatetime: an expiry without a time zone is refused at the door (AGENTS.md 3).
    expires_at: AwareDatetime

    @field_validator("expires_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class ConflictRead(BaseModel):
    """SCRUM-75 AC1: what the SCRUM-73 check says would block approving a request.
    SCRUM-83: `hold` when the clash is a tentative hold rather than a confirmed booking.

    SCRUM-82: the effective interval is carried as well as the event period, because the
    rule compares effective intervals (AC3/AC4). Quoting only the event period makes a
    refusal read as nonsense: a request at 21:14 reported as clashing with a booking from
    18:00 to 20:00 looks like no clash at all until the turnaround is visible.

    For a closure the two pairs are the same. A closure is not widened (AC5), so saying
    so plainly is better than leaving the reader to wonder whether it was.
    """

    kind: Literal["booking", "hold", "unavailability"]
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    effective_start_at: datetime
    effective_end_at: datetime
    message: str

    @classmethod
    def from_error(
        cls, exc: ConflictingBookingError | VenueUnavailableError, buffers: VenueBuffers
    ) -> Self:
        if isinstance(exc, ConflictingBookingError):
            booking = exc.booking
            held_from, held_to = effective_interval(booking.start_at, booking.end_at, buffers)
            return cls(
                kind="hold" if booking.status is BookingStatus.TENTATIVE else "booking",
                id=booking.id,
                start_at=booking.start_at,
                end_at=booking.end_at,
                effective_start_at=held_from,
                effective_end_at=held_to,
                message=str(exc),
            )
        period = exc.period
        return cls(
            kind="unavailability",
            id=period.id,
            start_at=period.starts_at,
            end_at=period.ends_at,
            effective_start_at=period.starts_at,
            effective_end_at=period.ends_at,
            message=str(exc),
        )


class VenueBookingDecisionRead(BaseModel):
    """A booking request as Venue Staff see it: what, where, when, and the decision."""

    id: uuid.UUID
    status: BookingStatus
    venue_id: uuid.UUID
    venue_name: str
    venue_location: str
    event_request_id: uuid.UUID
    event_name: str | None
    # SCRUM-111: which session of the parent event this request is for.
    session_label: str
    start_at: datetime
    end_at: datetime
    # SCRUM-82 AC3: the period the venue is actually held for, and the buffers that made
    # it wider, so Venue Staff can see why two requests that look apart are not.
    effective_start_at: datetime
    effective_end_at: datetime
    setup_minutes: int
    turnaround_minutes: int
    expected_attendance: int | None
    venue_requirement: str | None
    accessibility_requirement: str | None
    # SCRUM-43: what the event needs now, from the records the Coordinator maintains,
    # not the single string the organiser submitted. Nothing writes back to that string
    # (ADR-0033), so it goes stale the moment a requirement is added, changed or removed,
    # and Venue Staff were deciding on a stale answer. Each entry reads "Projector x2".
    equipment_requirements: list[str]
    layout_requirement: str | None
    requested_by_id: uuid.UUID
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    decision_reason: str | None
    # SCRUM-83: the hold, when Venue Staff placed one, and the event's assigned
    # Coordinator it is held for (AC1).
    expires_at: datetime | None = None
    held_by_id: uuid.UUID | None = None
    held_at: datetime | None = None
    coordinator_id: uuid.UUID | None = None
    conflict: ConflictRead | None = None

    @classmethod
    def from_context(
        cls,
        booking: VenueBooking,
        event: EventRequest,
        venue: Venue,
        conflict: BookingConflictError | None,
        requirements: Sequence[EventEquipmentRequirement],
    ) -> Self:
        buffers = VenueBuffers(
            setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
        )
        held_from, held_to = effective_interval(booking.start_at, booking.end_at, buffers)
        return cls(
            id=booking.id,
            status=booking.status,
            venue_id=venue.id,
            venue_name=venue.name,
            venue_location=venue.location,
            event_request_id=event.id,
            event_name=event.name,
            session_label=booking.session_label,
            start_at=booking.start_at,
            end_at=booking.end_at,
            # From the venue as it is now, not the stored snapshot. The conflict beside
            # it is computed live, and a stale snapshot (ADR-0019, the thing SCRUM-89
            # reports) would have the two lines on one card contradicting each other.
            effective_start_at=held_from,
            effective_end_at=held_to,
            setup_minutes=venue.setup_minutes,
            turnaround_minutes=venue.turnaround_minutes,
            expected_attendance=event.expected_attendance,
            venue_requirement=event.venue_requirement,
            accessibility_requirement=event.accessibility_requirement,
            equipment_requirements=[_describe(row) for row in requirements],
            layout_requirement=event.layout_requirement,
            requested_by_id=booking.requested_by_id,
            decided_by_id=booking.decided_by_id,
            decided_at=booking.decided_at,
            decision_reason=booking.decision_reason,
            expires_at=booking.expires_at,
            held_by_id=booking.held_by_id,
            held_at=booking.held_at,
            coordinator_id=event.coordinator_id,
            conflict=_conflict_read(conflict, venue),
        )


def _describe(requirement: EventEquipmentRequirement) -> str:
    """One requirement as a line Venue Staff can read: the type and how many."""
    return f"{requirement.equipment_type} x{requirement.quantity}"


def _conflict_read(exc: BookingConflictError | None, venue: Venue) -> ConflictRead | None:
    """Only the two named conflicts can come from the read-only SCRUM-73 check."""
    if isinstance(exc, (ConflictingBookingError, VenueUnavailableError)):
        buffers = VenueBuffers(
            setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
        )
        return ConflictRead.from_error(exc, buffers)
    return None
