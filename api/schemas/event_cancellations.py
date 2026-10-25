"""API contracts for cancelling an event and its requests (SCRUM-115)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.event_cancellation import TEXT_MAX_LENGTH
from models.event_cancellation_request import EventCancellationRequest
from models.event_request import EventRequest


class CancellationRequestInput(BaseModel):
    """AC1: the Organiser's reason. Blank is refused by the domain rule, with a field."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH * 2)


class CancelInput(BaseModel):
    """AC1, AC3: the Coordinator's reason, and the request being applied, if any.

    When a request is applied without a reason, its own reason is recorded.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH * 2)
    request_id: uuid.UUID | None = None


class DeclineInput(BaseModel):
    """AC1: why the Coordinator declined the request. Required."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH * 2)


class CancellationRequestRead(BaseModel):
    """One request and, once decided, its outcome."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    reason: str
    requested_by_id: uuid.UUID
    requested_at: datetime
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None


class CancellationRead(BaseModel):
    """AC1, AC3: the event's cancellation, if any, and every request, oldest first."""

    event_request_id: uuid.UUID
    status: str
    cancelled_by_id: uuid.UUID | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    requests: list[CancellationRequestRead]

    @classmethod
    def of(
        cls, event: EventRequest, requests: list[EventCancellationRequest]
    ) -> "CancellationRead":
        return cls(
            event_request_id=event.id,
            status=event.status.value,
            cancelled_by_id=event.cancelled_by_id,
            cancelled_at=event.cancelled_at,
            cancellation_reason=event.cancellation_reason,
            requests=[CancellationRequestRead.model_validate(row) for row in requests],
        )
