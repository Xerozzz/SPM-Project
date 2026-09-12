"""Request/response contracts for event requests (SCRUM-46)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from domain.event_status import EventStatus


class EventRequestUpdate(BaseModel):
    """Fields an organiser may change on a draft. All optional: a PATCH sends only what
    changed, and a draft is allowed to be incomplete until it is submitted."""

    name: str | None = None
    purpose: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    expected_attendance: int | None = None
    venue_requirement: str | None = None
    accessibility_requirement: str | None = None
    equipment_requirement: str | None = None
    layout_requirement: str | None = None
    registration_requirement: str | None = None


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
