"""Venue booking request contracts (SCRUM-38, SCRUM-74)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from domain.venue_booking import BookingStatus
from schemas.venue_booking_decisions import ConflictRead


class VenueBookingCreate(BaseModel):
    venue_id: uuid.UUID


class SuitabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mismatch_codes: list[str]
    expected_attendance: int
    venue_capacity: int
    unavailable_facilities: list[str]
    accessibility_need: str | None
    venue_accessibility: list[str]
    layout_need: str | None
    venue_layouts: list[str]


class VenueBookingSubmissionRead(BaseModel):
    id: uuid.UUID
    venue_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    suitability: SuitabilityRead


class VenueBookingRead(BaseModel):
    """A booking after a decision (SCRUM-74 approve)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    venue_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    # SCRUM-89 AC4: set when the venue's current buffers mean this booking can no longer
    # stand beside everything else at that venue. Derived on every read rather than
    # stored, so it appears and disappears on its own as the venue changes (AC3, AC7).
    conflict: ConflictRead | None = None
