"""API contracts for arrangement reminders (SCRUM-85)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.event_reminder import EventReminder


class ReminderRead(BaseModel):
    """AC2: one configured lead time, and whether its occurrence has happened yet."""

    id: uuid.UUID
    event_request_id: uuid.UUID
    lead_minutes: int
    #: AC6 and AC8: processed occurrences are history. Shown so the Coordinator can see
    #: which reminders have already been through rather than wondering why one is quiet.
    processed_at: datetime | None

    @classmethod
    def of(cls, reminder: EventReminder) -> "ReminderRead":
        return cls(
            id=reminder.id,
            event_request_id=reminder.event_request_id,
            lead_minutes=reminder.lead_minutes,
            processed_at=reminder.processed_at,
        )


class ReminderScheduleWrite(BaseModel):
    """AC1: the whole schedule, replacing whatever was there.

    `lead_minutes` is typed loosely on purpose. Pydantic would coerce `1.0` to `1` and
    `True` to `1` before the domain ever saw them, which is the opposite of AC1's
    "fractional offsets are refused": the rule that decides what a lead time is lives in
    `domain.event_reminder`, so the request carries the values to it unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    lead_minutes: list[object]
