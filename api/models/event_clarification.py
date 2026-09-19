"""Clarification messages exchanged while an event request is reviewed (SCRUM-30)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from domain.event_clarification import ClarificationKind


class EventClarification(Base):
    """One coordinator request or organiser response retained with an event request."""

    __tablename__ = "event_clarifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # Which side wrote it. Same storage choice as EventRequest.status: the enum's
    # lowercase value in a VARCHAR, so adding a kind later is a code change only.
    kind: Mapped[ClarificationKind] = mapped_column(
        Enum(
            ClarificationKind,
            native_enum=False,
            length=20,
            values_callable=lambda members: [m.value for m in members],
        ),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
