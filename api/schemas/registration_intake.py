"""HTTP contracts for SCRUM-113's separate operational registration settings."""

import uuid
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, field_validator

from domain.registration_intake import intake_is_open, is_enabled
from models.event_request import EventRequest
from services import registration_intake as service


class RegistrationOpen(BaseModel):
    closes_at: AwareDatetime | None = None

    @field_validator("closes_at")
    @classmethod
    def to_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else value.astimezone(UTC)


class RegistrationExtension(BaseModel):
    closes_at: AwareDatetime

    @field_validator("closes_at")
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class RegistrationSettingsRead(BaseModel):
    event_request_id: uuid.UUID
    registration_enabled: bool
    opened_at: datetime | None
    closes_at: datetime | None
    suspended_at: datetime | None
    intake_open: bool

    @classmethod
    def of(cls, event: EventRequest, now: datetime) -> "RegistrationSettingsRead":
        settings = service.settings_of(event)
        return cls(
            event_request_id=event.id,
            registration_enabled=is_enabled(event.registration_requirement),
            opened_at=settings.opened_at,
            closes_at=settings.closes_at,
            suspended_at=settings.suspended_at,
            intake_open=intake_is_open(event.status, settings, now),
        )
