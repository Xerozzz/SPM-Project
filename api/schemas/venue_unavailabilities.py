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
