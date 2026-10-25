"""API contracts for completing an event and its closure record (SCRUM-86)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.event_completion import NOTES_MAX_LENGTH
from models.event_closure_note import EventClosureNote
from models.event_request import EventRequest


class ClosureInput(BaseModel):
    """AC3: what the Coordinator records. Both parts may be left out.

    Attendance is a whole number. The domain rule refuses a negative one with a named
    field, so it is not bounded here as well.
    """

    model_config = ConfigDict(extra="forbid")

    actual_attendance: int | None = None
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH * 2)


class ClosureNoteRead(BaseModel):
    """One version of the closure record, as it was recorded."""

    model_config = ConfigDict(from_attributes=True)

    version: int
    actual_attendance: int | None
    notes: str | None
    recorded_by_id: uuid.UUID
    recorded_at: datetime


class ClosureRead(BaseModel):
    """AC2, AC4, AC5: the completion and every version of the closure record."""

    event_request_id: uuid.UUID
    status: str
    completed_by_id: uuid.UUID | None
    completed_at: datetime | None
    #: The newest version, or null before completion.
    current: ClosureNoteRead | None
    #: Every version, oldest first.
    history: list[ClosureNoteRead]

    @classmethod
    def of(cls, event: EventRequest, notes: list[EventClosureNote]) -> "ClosureRead":
        versions = [ClosureNoteRead.model_validate(note) for note in notes]
        return cls(
            event_request_id=event.id,
            status=event.status.value,
            completed_by_id=event.completed_by_id,
            completed_at=event.completed_at,
            current=versions[-1] if versions else None,
            history=versions,
        )
