"""API contracts for the venue catalogue (SCRUM-59, SCRUM-82). Mirrors domain/venue.py."""

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
    # SCRUM-82 AC1: `int` is what refuses a non-numeric buffer, with the field named in
    # the Pydantic error. Whether the number is acceptable is domain/venue.py's decision,
    # as for maximum_capacity. Absent means no buffer, so an existing payload still saves.
    setup_minutes: int | None = None
    turnaround_minutes: int | None = None


class VenueUpdate(VenueCreate):
    """Fields Venue Staff may change. All optional: a PATCH sends only what changed, and
    the service validates the record as it would be afterwards."""


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
    # SCRUM-82 AC2: readable by anyone who may read the catalogue, so an Event Coordinator
    # can see the buffers. Only Venue Staff reach the POST and PATCH routes that set them.
    setup_minutes: int
    turnaround_minutes: int
    is_active: bool


class VenueProblemRead(BaseModel):
    """One field Venue Staff must fix before the record can be saved (AC5)."""

    field: str
    reason: str
