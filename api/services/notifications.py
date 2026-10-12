"""Notification inbox orchestration for SCRUM-99.

The recipient always comes from the signed token, never from browser input. Reads
and writes go through the recipient-scoped repository, so one user can never reach
another's rows. Every failure is a typed exception so the router maps it without
knowing the rules.
"""

import uuid
from datetime import datetime

from core.database import Session
from models.notification import Notification
from repositories import notifications as repo


class NotificationError(Exception):
    """Base for every failure this service reports."""


class NotificationNotFoundError(NotificationError):
    """No notification with that id belongs to this recipient.

    Raised for another user's row exactly as for a missing id, so callers cannot
    probe whether someone else's notification exists.
    """


def list_inbox(db: Session, recipient_id: uuid.UUID) -> list[Notification]:
    """The recipient's notifications, newest first."""
    return repo.list_for_recipient(db, recipient_id)


def mark_viewed(
    db: Session, notification_id: uuid.UUID, recipient_id: uuid.UUID, now: datetime
) -> Notification:
    """Mark one owned notification viewed; a repeated mark keeps the first time."""
    notification = repo.get_for_recipient(db, notification_id, recipient_id)
    if notification is None:
        raise NotificationNotFoundError
    return repo.mark_viewed(db, notification, now)
