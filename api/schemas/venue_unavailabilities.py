"""HTTP contracts for SCRUM-62 venue closures."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VenueUnavailabilityWrite(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reason: str | None = None


class VenueUnavailabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    venue_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    reason: str


class AffectedArrangementRead(BaseModel):
    """SCRUM-81 AC2: one arrangement a saved closure runs into."""

    booking_id: uuid.UUID
    event_request_id: uuid.UUID
    event_name: str | None
    session_label: str
    start_at: datetime
    end_at: datetime
    status: str


class VenueUnavailabilitySaved(VenueUnavailabilityRead):
    """A saved closure plus the live arrangements it affects (SCRUM-81 AC2)."""

    affected: list[AffectedArrangementRead]
