"""Request/response contracts for event requests (SCRUM-46)."""

import uuid
from datetime import UTC, datetime

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    computed_field,
    field_validator,
)

from domain.event_status import EventAction, EventStatus, allowed_actions


class EventRequestCreate(BaseModel):
    """The complete information collected when an organiser creates an event request (SCRUM-28).

    The separate submit endpoint is responsible for moving a created request to review.
    """

    name: str
    purpose: str
    description: str
    start_at: AwareDatetime
    end_at: AwareDatetime
    expected_attendance: int
    venue_requirement: str
    accessibility_requirement: str
    equipment_requirement: str
    layout_requirement: str
    registration_requirement: str

    @field_validator("start_at", "end_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class EventRequestUpdate(BaseModel):
    """Fields an organiser may change on a draft. All optional: a PATCH sends only what
    changed, and a draft is allowed to be incomplete until it is submitted."""

    # extra="forbid": a field name the API does not know (a typo such as "descripton") is
    # a 422, not a silent no-op that leaves the organiser thinking their edit was saved.
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    purpose: str | None = None
    description: str | None = None
    # AwareDatetime: a value without a UTC offset is rejected at the door (AGENTS.md §3),
    # so a naive datetime can never reach the database through this endpoint ...
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    expected_attendance: int | None = None
    venue_requirement: str | None = None
    accessibility_requirement: str | None = None
    equipment_requirement: str | None = None
    layout_requirement: str | None = None
    registration_requirement: str | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _to_utc(cls, value: datetime | None) -> datetime | None:
        """... and an aware one in another zone is converted, so the invariant is UTC at
        every layer rather than merely "has a timezone". The instant is unchanged."""
        return None if value is None else value.astimezone(UTC)


class EventRequestDraftCreate(EventRequestUpdate):
    """Fields an organiser may provide when first saving a draft.

    Same optional contract as an update: SCRUM-29 allows a draft to be incomplete until
    the organiser chooses to submit it.
    """


class EventRequestRead(BaseModel):
    """An event request as the organiser sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: EventStatus
    name: str | None
    purpose: str | None
    description: str | None
    start_at: datetime | None
    end_at: datetime | None
    expected_attendance: int | None
    venue_requirement: str | None
    accessibility_requirement: str | None
    equipment_requirement: str | None
    layout_requirement: str | None
    registration_requirement: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    # SCRUM-34: who was auto-assigned on first submission, and when.
    coordinator_id: uuid.UUID | None
    assigned_at: datetime | None
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    rejection_reason: str | None


class EventRequestRejection(BaseModel):
    """The reason required before a coordinator can reject a request."""

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("is required")
        return value


class FieldProblemRead(BaseModel):
    """One field the organiser must fix before the request can be submitted (AC2)."""

    field: str
    reason: str
