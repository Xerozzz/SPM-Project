"""Attendee-safe event and registration response contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class RegistrationSubmit(BaseModel):
    """The attendee-supplied contact information retained with this submission."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(max_length=200)
    age: int = Field(ge=0)
    phone_number: str = Field(max_length=50)
    dietary_accessibility_notes: str | None = None

    @field_validator("full_name", "phone_number")
    @classmethod
    def required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("is required")
        return cleaned

    @field_validator("dietary_accessibility_notes")
    @classmethod
    def optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


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
