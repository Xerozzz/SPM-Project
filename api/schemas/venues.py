"""API contracts for the venue catalogue (SCRUM-59). Mirrors models/venue.py."""

import uuid
from datetime import time

from pydantic import BaseModel, ConfigDict


class VenueRead(BaseModel):
    """A venue as the catalogue shows it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location: str
    maximum_capacity: int
    facilities: list[str]
    supported_layouts: list[str]
    accessibility_features: list[str]
    opens_at: time
    closes_at: time
    is_active: bool
