"""Request/response contracts for event requests (SCRUM-46)."""

import uuid
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator

from domain.event_status import EventStatus


class EventRequestUpdate(BaseModel):
    """Fields an organiser may change on a draft. All optional: a PATCH sends only what
    changed, and a draft is allowed to be incomplete until it is submitted."""

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


class FieldProblemRead(BaseModel):
    """One field the organiser must fix before the request can be submitted (AC2)."""

    field: str
    reason: str
