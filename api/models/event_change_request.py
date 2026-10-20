"""An Organiser's significant-change request and its items (SCRUM-37, ADR-0041).

One request holds the reason and who asked when; each item is one changed value with the
value it would replace (AC3). Values are JSONB because they are dates, numbers, text or a
whole equipment line, and the item says which. Nothing here is applied to the event:
SCRUM-47 decides and applies a request.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from domain.event_change import ChangeRequestStatus


class EventChangeRequest(Base):
    """One proposal of significant changes to one event."""

    __tablename__ = "event_change_requests"
    __table_args__ = (
        # AC8: the client sends one key per submit action. A retry of the same action
        # finds the request this key already made instead of creating a second one.
        UniqueConstraint(
            "event_request_id", "submission_key", name="event_change_requests_one_per_submission"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    submission_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ChangeRequestStatus.PENDING
    )
    # AC3: the event version the proposal was made against. SCRUM-47 compares it, and each
    # item's current value, with the event when deciding, so a stale request is caught.
    event_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["EventChangeItem"]] = relationship(
        order_by="EventChangeItem.position", cascade="all, delete-orphan"
    )


class EventChangeItem(Base):
    """One proposed change: what it changes, the current value and the proposed one."""

    __tablename__ = "event_change_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_change_requests.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(nullable=False)
    # event, session or equipment (domain.event_change.ChangeTarget).
    target: Mapped[str] = mapped_column(String(20), nullable=False)
    # The venue booking or equipment line changed; null for the event itself and for an
    # equipment line being added.
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    field: Mapped[str] = mapped_column(String(60), nullable=False)
    current_value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    proposed_value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
