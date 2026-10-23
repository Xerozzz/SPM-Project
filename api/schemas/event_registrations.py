"""Attendee-safe event and registration response contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from domain.registration import RegistrationStatus
from models.event_registration import EventRegistration


class AttendeeEventRead(BaseModel):
    """The confirmed event fields appropriate to a prospective attendee."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    description: str | None
    start_at: datetime | None
    end_at: datetime | None


class RegistrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_request_id: uuid.UUID
    status: RegistrationStatus
    submitted_at: datetime
    submission_order: int

    @classmethod
    def of(cls, registration: EventRegistration) -> "RegistrationRead":
        return cls.model_validate(registration)
