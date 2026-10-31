"""Notification inbox orchestration for SCRUM-99.

The recipient always comes from the signed token, never from browser input. Reads
and writes go through the recipient-scoped repository, so one user can never reach
another's rows. Every failure is a typed exception so the router maps it without
knowing the rules.
"""

import uuid
from datetime import datetime

from core.database import Session
from repositories import notifications as repo
from schemas.notifications import NotificationRead


class NotificationError(Exception):
    """Base for every failure this service reports."""


class NotificationNotFoundError(NotificationError):
    """No notification with that id belongs to this recipient.

    Raised for another user's row exactly as for a missing id, so callers cannot
    probe whether someone else's notification exists.
    """


def list_inbox(db: Session, recipient_id: uuid.UUID) -> list[NotificationRead]:
    """The recipient's notifications, newest first."""
    names = repo.event_names_for_recipient(db, recipient_id)
    return [
        NotificationRead.model_validate(row).model_copy(
            update={"event_name": names.get(row.event_request_id)}
        )
        for row in repo.list_for_recipient(db, recipient_id)
    ]


def mark_viewed(
    db: Session, notification_id: uuid.UUID, recipient_id: uuid.UUID, now: datetime
) -> NotificationRead:
    """Mark one owned notification viewed; a repeated mark keeps the first time."""
    notification = repo.get_for_recipient(db, notification_id, recipient_id)
    if notification is None:
        raise NotificationNotFoundError
    row = repo.mark_viewed(db, notification, now)
    names = repo.event_names_for_recipient(db, recipient_id)
    return NotificationRead.model_validate(row).model_copy(
        update={"event_name": names.get(row.event_request_id)}
    )
