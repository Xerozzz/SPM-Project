"""API contracts for event-review clarification messages (SCRUM-30)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from domain.event_clarification import ClarificationKind


class EventClarificationCreate(BaseModel):
    """Free text supplied by a coordinator or organiser."""

    message: str

    @field_validator("message")
    @classmethod
    def _message_must_not_be_blank(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("message must not be blank")
        return message


class EventClarificationRead(BaseModel):
    """One retained entry in an event's clarification history."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_request_id: uuid.UUID
    author_id: uuid.UUID
    kind: ClarificationKind
    message: str
    created_at: datetime
