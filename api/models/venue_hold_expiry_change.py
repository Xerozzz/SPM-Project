"""A record of Venue Staff changing a tentative hold's expiry (SCRUM-136, ADR-0070).

SCRUM-121 replaces `venue_bookings.expires_at`; this row keeps what it was, what it became,
who changed it and when. Written in the same transaction as the update and never changed
afterwards. An update to the same expiry is not a change and writes no row.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class VenueHoldExpiryChange(Base):
    """One change to one hold's expiry."""

    __tablename__ = "venue_hold_expiry_changes"
    __table_args__ = (
        CheckConstraint(
            "old_expires_at <> new_expires_at", name="venue_hold_expiry_changes_is_a_change"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("venue_bookings.id"), nullable=False, index=True
    )
    old_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    new_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
