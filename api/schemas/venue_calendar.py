"""Venue availability calendar contracts (SCRUM-54)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


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
