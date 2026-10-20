"""What one saved venue closure affected, as it was when saved (SCRUM-81).

One row per create or update of a closure that hit at least one live arrangement. It is
a snapshot for history (SCRUM-88) and for starting a replacement (SCRUM-116): the
affected booking ids, the period and reason at the time, and who saved it. It never
changes afterwards. What needs action *now* is derived on every read (SCRUM-89), so this
row is never the thing a screen trusts for the current state.

`unavailability_id` has no foreign key on purpose: a closure can be deleted (SCRUM-62),
and the record that it once affected these arrangements must outlive it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class VenueClosureImpact(Base):
    __tablename__ = "venue_closure_impacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unavailability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    venue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("venues.id"), nullable=False, index=True
    )
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    affected_booking_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
