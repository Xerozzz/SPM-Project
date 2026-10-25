"""An Organiser's request to cancel their event (SCRUM-115 AC1, ADR-0061).

The current assigned Coordinator applies it, which cancels the event, or declines it with
a note. Rows are kept after a decision, so every request and its outcome stay. At most
one request per event is pending at a time.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from domain.event_cancellation import RequestStatus


class EventCancellationRequest(Base):
    __tablename__ = "event_cancellation_requests"
    __table_args__ = (
        Index(
            "uq_event_cancellation_requests_one_pending",
            "event_request_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    status: Mapped[RequestStatus] = mapped_column(
        Enum(
            RequestStatus,
            native_enum=False,
            length=20,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=RequestStatus.PENDING,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Why the Coordinator declined. Empty when applied.
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
