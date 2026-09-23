"""API contracts for the venue catalogue (SCRUM-59). Mirrors domain/venue.py."""

import uuid
from datetime import time

from pydantic import BaseModel, ConfigDict


class VenueCreate(BaseModel):
    """Everything Venue Staff supply when adding a venue.

    Required here only in the sense of "present in the payload"; whether each value is
    acceptable is domain/venue.py's decision, so one missing field and one invalid field
    are reported the same way (AC5) instead of one as a 422 body and the other as a
    Pydantic error in a different shape.
    """

    name: str | None = None
    location: str | None = None
    maximum_capacity: int | None = None
    facilities: list[str] | None = None
    supported_layouts: list[str] | None = None
    accessibility_features: list[str] | None = None
    opens_at: time | None = None
    closes_at: time | None = None


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


class VenueProblemRead(BaseModel):
    """One field Venue Staff must fix before the record can be saved (AC5)."""

    field: str
    reason: str
