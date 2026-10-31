"""API contracts for the in-app notification inbox (SCRUM-99)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from domain.notifications import NotificationSource, NotificationType


class NotificationRead(BaseModel):
    """One inbox entry: the related event, the triggering action, and when it happened.

    `is_unread` derives from `viewed_at` so the UI never guesses unread state from
    anything else. Only the fields the acceptance criteria require — no unrelated
    private fields.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_request_id: uuid.UUID
    event_name: str | None = None
    type: NotificationType
    source_type: NotificationSource
    source_id: str
    occurred_at: datetime
    created_at: datetime
    viewed_at: datetime | None

    @computed_field
    def is_unread(self) -> bool:
        """Unread means never viewed; marking viewed keeps the row visible."""
        return self.viewed_at is None
