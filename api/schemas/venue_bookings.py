"""Venue booking request contracts (SCRUM-38, SCRUM-74, session fields SCRUM-111)."""

import uuid
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from domain.venue_booking import BookingStatus
from domain.venue_session import MAX_SESSION_LABEL_LENGTH
from schemas.venue_booking_decisions import ConflictRead


class VenueBookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue_id: uuid.UUID
    # SCRUM-111: which session of the parent event this request is for, and the period
    # that session needs the venue for. AwareDatetime refuses a naive instant at the
    # door (AGENTS.md 3); the domain checks the rest against the parent event period.
    session_label: str = Field(max_length=MAX_SESSION_LABEL_LENGTH)
    start_at: AwareDatetime
    end_at: AwareDatetime
    # SCRUM-116: set when this request replaces an affected arrangement of the event.
    replaces_booking_id: uuid.UUID | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class VenueBookingCancel(BaseModel):
    """SCRUM-109: why the assigned Coordinator cancels one arrangement.

    Optional here so a missing reason gets the same field error as a blank one, from the
    one rule in domain.venue_cancellation (AC4), rather than a differently shaped 422.
    """

    reason: str | None = None


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
    session_label: str
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    suitability: SuitabilityRead
    # SCRUM-116: the arrangement this request replaces, if any.
    replaces_booking_id: uuid.UUID | None = None


class VenueBookingRead(BaseModel):
    """A booking after a decision (SCRUM-74 approve)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    venue_id: uuid.UUID
    # SCRUM-111: which session of the parent event this request is for.
    session_label: str
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    # SCRUM-82 AC3: the period the venue is actually held for, so a clash the Coordinator
    # is shown adds up. Without it a booking at 21:14 reads as clashing with one that
    # finished at 20:00, and the 45 minutes of turnaround explaining it are nowhere.
    # Derived from the venue's current buffers rather than the stored snapshot, because
    # that snapshot is what SCRUM-89 exists to report as stale (ADR-0019).
    effective_start_at: datetime | None = None
    effective_end_at: datetime | None = None
    # SCRUM-83 AC2: when a tentative hold on this request ends.
    expires_at: datetime | None = None
    # SCRUM-116 AC3: the arrangement this request replaces, so old and new stay linked.
    replaces_booking_id: uuid.UUID | None = None
    # SCRUM-109 AC2, AC11: who cancelled this arrangement, when, and why. Empty unless
    # it is cancelled; its decision and hold history stay in the fields above.
    cancelled_by_id: uuid.UUID | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    # SCRUM-89 AC4: set when the venue's current buffers mean this booking can no longer
    # stand beside everything else at that venue. Derived on every read rather than
    # stored, so it appears and disappears on its own as the venue changes (AC3, AC7).
    conflict: ConflictRead | None = None
