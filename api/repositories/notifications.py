"""Persistence for in-app notifications (SCRUM-99).

Every query is scoped by recipient ID: a caller can only ever read or change their
own rows. Inbox order is newest first with id as the stable secondary key for equal
occurrence times. See ADR-0022.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from domain.notifications import NotificationSource, NotificationType
from models.notification import Notification


def list_for_recipient(db: Session, recipient_id: uuid.UUID) -> list[Notification]:
    """The recipient's inbox, newest occurrence first with id as the tiebreak."""
    statement = (
        select(Notification)
        .where(Notification.recipient_id == recipient_id)
        .order_by(Notification.occurred_at.desc(), Notification.id.desc())
    )
    return list(db.scalars(statement))


def get_for_recipient(
    db: Session, notification_id: uuid.UUID, recipient_id: uuid.UUID
) -> Notification | None:
    """One notification, only when it belongs to the recipient.

    Returns None for another user's row exactly as for a missing id, so the API
    discloses neither content nor ownership (TC-99-05).
    """
    statement = select(Notification).where(
        Notification.id == notification_id,
        Notification.recipient_id == recipient_id,
    )
    return db.scalars(statement).first()


def stage(
    db: Session,
    recipient_id: uuid.UUID,
    event_request_id: uuid.UUID,
    type: NotificationType,
    source_type: NotificationSource,
    source_id: str,
    occurred_at: datetime,
) -> None:
    """Stage one recipient notification in the current transaction (no commit).

    Retrying the same source action is a no-op: the unique
    (recipient, source_type, source_id) constraint collides and ON CONFLICT DO
    NOTHING keeps the first row. Callers commit with their business write so both
    land or roll back together.
    """
    statement = (
        insert(Notification)
        .values(
            recipient_id=recipient_id,
            event_request_id=event_request_id,
            type=type.value,
            source_type=source_type.value,
            source_id=source_id,
            occurred_at=occurred_at,
        )
        .on_conflict_do_nothing(
            index_elements=["recipient_id", "source_type", "source_id"],
        )
    )
    db.execute(statement)


def mark_viewed(db: Session, notification: Notification, now: datetime) -> Notification:
    """Record the viewed time; a repeated mark keeps the first time (idempotent)."""
    if notification.viewed_at is None:
        notification.viewed_at = now
        db.add(notification)
        db.commit()
        db.refresh(notification)
    return notification
