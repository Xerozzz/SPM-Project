"""A bookable space in the ConnectSphere venue catalogue (SCRUM-59)."""

import uuid
from datetime import UTC, datetime, time

from sqlalchemy import Boolean, DateTime, Integer, String, Time
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Venue(Base):
    """One venue record, maintained by Venue Staff and read by everyone else.

    A venue is never deleted: `is_active` is cleared instead, so an event or booking that
    already references it keeps a readable record (AC4). See ADR-0012.
    """

    __tablename__ = "venues"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Unique so a coordinator reading "Hall A" on a booking knows exactly which space it is.
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    maximum_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Postgres-dialect ARRAY, as in models/user.py: the generic one has no `.contains()`,
    # which repositories/venues.py needs to filter the catalogue by layout.
    facilities: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    supported_layouts: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, default=list
    )
    accessibility_features: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list
    )
    # Wall-clock opening hours, not instants: see the note in domain/venue.py for why these
    # are `Time` and outside AGENTS.md's timezone-aware-UTC rule.
    opens_at: Mapped[time] = mapped_column(Time, nullable=False)
    closes_at: Mapped[time] = mapped_column(Time, nullable=False)
    # SCRUM-82: preparation and reset minutes the venue needs either side of a booking.
    # Zero is the default so every venue that existed before this column behaves exactly
    # as it did (AC7). They live here, not on venue_bookings, so a booking cannot override
    # them (AC1).
    setup_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    turnaround_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # SCRUM-59: a deactivated venue stays readable but cannot be chosen for new work (AC3).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
