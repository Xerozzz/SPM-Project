"""A record of Venue Staff changing a venue's setup or turnaround time (SCRUM-89 AC8).

The one thing this story stores. Whether a booking is problematic is derived from the
venue's current buffers every time it is read, so it can never be stale (AC3, AC7); this
row is the opposite, a statement about one moment that must not change afterwards.

`flagged_booking_ids` is a snapshot of what the change caught out when it was saved, not
a live relationship, which is why it is an array of ids rather than a join table with
foreign keys. Re-reading it later tells you what the actor was told at the time, which is
the point of an audit record; what is problematic *now* is a different question with a
different answer.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class VenueBufferChange(Base):
    """One saved change to a venue's buffers, and what it made problematic."""

    __tablename__ = "venue_buffer_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("venues.id"), nullable=False, index=True
    )
    changed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    # Both sides of the change, so the record stands on its own without reading the row
    # before it. AC8 asks for the old and new values.
    old_setup_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    old_turnaround_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    new_setup_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    new_turnaround_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    flagged_booking_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
