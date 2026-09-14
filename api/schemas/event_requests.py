"""Request/response contracts for event requests (SCRUM-46)."""

import uuid
from datetime import UTC, datetime

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    computed_field,
    ValidationInfo,
    field_validator,
)

from domain.event_status import EventAction, EventStatus, allowed_actions


class EventRequestCreate(BaseModel):
    """The complete information collected when an organiser starts a new draft (SCRUM-28).

    A request created through this form is deliberately still a draft.  The separate submit
    endpoint is the only operation that moves it to review.
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

    @field_validator(
        "name",
        "purpose",
        "description",
        "venue_requirement",
        "accessibility_requirement",
        "equipment_requirement",
        "layout_requirement",
        "registration_requirement",
    )
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("is required")
        return value

    @field_validator("start_at", "end_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("expected_attendance")
    @classmethod
    def _positive_attendance(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be a positive whole number")
        return value

    @field_validator("end_at")
    @classmethod
    def _end_after_start(cls, value: datetime, info: ValidationInfo) -> datetime:
        start_at = info.data.get("start_at")
        if isinstance(start_at, datetime) and value <= start_at:
            raise ValueError("must be after start_at")
        return value


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
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    rejection_reason: str | None
    clarification_requested_by_id: uuid.UUID | None
    clarification_requested_at: datetime | None
    clarification_request: str | None

    @computed_field
    def status_permits(self) -> list[EventAction]:
        """SCRUM-35: what this request's status permits, sorted for a stable response.

        Named for the status, not the caller: it does not know who is asking, so a reader
        must not treat it as "what I may do". Authorisation is answered separately.
        """
        return sorted(allowed_actions(self.status))


class FieldProblemRead(BaseModel):
    """One field the organiser must fix before the request can be submitted (AC2)."""

    field: str
    reason: str
