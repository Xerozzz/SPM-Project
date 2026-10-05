"""A venue hold or request for one time slot (SCRUM-55/SCRUM-38).

Search (AC4/AC6) treats only `confirmed` rows as blocking: a pending request never
excludes a venue. The half-open overlap rule itself lives in domain/venue_search.py;
the repository issues the overlap query with bound parameters, never string SQL.
SCRUM-38 writes pending requests; SCRUM-74 confirms them. Migration 0012 adds the
ADR-0002 exclusion constraint `venue_bookings_no_confirmed_overlap`: no two confirmed
rows for one venue may overlap. It is declared only in the migration, because Alembic
autogenerate does not reflect EXCLUDE constraints.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from domain.venue_booking import BookingStatus


def _now() -> datetime:
    return datetime.now(UTC)


class VenueBooking(Base):
    """One hold on a venue for [start_at, end_at), stored as tz-aware UTC instants."""

    __tablename__ = "venue_bookings"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("venues.id"), nullable=False, index=True
    )
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Only "confirmed" blocks search (domain.venue_search). Stored as
    # the enum's lowercase value in a plain VARCHAR (native_enum=False), so adding a
    # status later is a code change, not a Postgres type migration (like EventRequest).
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            native_enum=False,
            length=20,
            values_callable=lambda members: [m.value for m in members],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    # SCRUM-40: the Venue Staff decision. Empty while the request is pending.
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
