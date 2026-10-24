"""One version of an event's closure record (SCRUM-86, ADR-0059).

Completing an event writes version 1, and every correction adds the next version. Rows
are never updated, so earlier values, who recorded them and when all stay (AC5). The
newest version is the current record.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class EventClosureNote(Base):
    __tablename__ = "event_closure_notes"
    __table_args__ = (
        UniqueConstraint("event_request_id", "version", name="event_closure_notes_one_version"),
        CheckConstraint(
            "actual_attendance IS NULL OR actual_attendance >= 0",
            name="event_closure_notes_attendance_not_negative",
        ),
        CheckConstraint("version >= 1", name="event_closure_notes_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: AC3: None when nobody recorded a count, which is not the same as zero.
    actual_attendance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
