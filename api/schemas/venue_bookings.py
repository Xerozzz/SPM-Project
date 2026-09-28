"""Venue booking request contracts (SCRUM-38)."""

import uuid

from pydantic import BaseModel, ConfigDict

from domain.venue_booking import BookingStatus


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
    status: BookingStatus
    suitability: SuitabilityRead
