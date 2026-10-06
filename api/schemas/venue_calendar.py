"""Venue availability calendar contracts (SCRUM-54, SCRUM-76, SCRUM-77)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from domain.venue_calendar import DetailsStatus


class CalendarEntryRead(BaseModel):
    """One calendar entry. `status` tells a confirmed booking, a pending request and an
    unavailability block apart (AC1)."""

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["booking", "unavailability"]
    id: uuid.UUID
    venue_id: uuid.UUID
    venue_name: str
    start_at: datetime
    end_at: datetime
    status: Literal["confirmed", "pending", "unavailable"]


class AvailabilityRead(BaseModel):
    """SCRUM-76: the verdict for one venue and period, with the entries behind it.

    `available` is true when no confirmed booking or closure overlaps the period and the
    venue is active. It says nothing is holding the venue, not that the venue is open:
    operating hours are not considered here.
    """

    model_config = ConfigDict(from_attributes=True)

    venue_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    available: bool
    entries: list[CalendarEntryRead]


class CalendarEntryDetailsRead(BaseModel):
    """SCRUM-77: one entry in full. `reason` is set for a closure, `event_request_id`
    for a booking."""

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["booking", "unavailability"]
    id: uuid.UUID
    venue_id: uuid.UUID
    venue_name: str
    venue_location: str
    start_at: datetime
    end_at: datetime
    status: DetailsStatus
    reason: str | None
    event_request_id: uuid.UUID | None
