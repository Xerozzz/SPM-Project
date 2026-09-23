"""A confirmed or pending hold on a venue for one time slot (SCRUM-55).

Search (AC4/AC6) treats only `confirmed` rows as blocking: a pending request never
excludes a venue. The half-open overlap rule itself lives in domain/venue_search.py;
the repository issues the overlap query with bound parameters, never string SQL.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class VenueBooking(Base):
    """One hold on a venue for [start_at, end_at), stored as tz-aware UTC instants."""

    __tablename__ = "venue_bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("venues.id"), nullable=False, index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # "confirmed" blocks search; "pending" does not (domain.venue_search).
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
