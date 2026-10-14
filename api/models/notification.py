"""One recipient's in-app notification (SCRUM-99).

One row per recipient per source action: the inbox reads only rows addressed to the
caller, and the unique (recipient, source_type, source_id) constraint makes retry
idempotence a database guarantee. No presentation HTML is stored — the UI renders
from type + event + time. See ADR-0022.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from domain.notifications import NotificationSource, NotificationType


def _now() -> datetime:
    return datetime.now(UTC)


class Notification(Base):
    """One unread-or-viewed inbox entry addressed to a single user."""

    __tablename__ = "notifications"
    __table_args__ = (
        # One notification per recipient per source action: retrying the same action
        # collides instead of duplicating. Distinct actions stay distinct because the
        # source pair names the exact triggering record, not just the event.
        UniqueConstraint(
            "recipient_id", "source_type", "source_id", name="uq_notification_recipient_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    # Stored as stable string values (native_enum=False), so adding a type later is a
    # code change, not a Postgres type migration — same choice as EventRequest.status.
    type: Mapped[NotificationType] = mapped_column(
        Enum(
            NotificationType,
            native_enum=False,
            length=50,
            values_callable=lambda members: [m.value for m in members],
        ),
        nullable=False,
    )
    source_type: Mapped[NotificationSource] = mapped_column(
        Enum(
            NotificationSource,
            native_enum=False,
            length=50,
            values_callable=lambda members: [m.value for m in members],
        ),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # When the triggering action happened (copied from the source record), and when
    # the row was stored. Both timezone-aware UTC; viewed_at is null until viewed.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
