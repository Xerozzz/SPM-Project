"""One coordinator ownership change for an event request (SCRUM-97).

Append-only by contract: application flows insert rows and never update or delete
them. The first assignment records `previous_coordinator_id=None`; every
reassignment records who owned it before, who owns it now, which Lead moved it,
and when (timezone-aware UTC). Current ownership stays on the event request row
for cheap authorisation; this table is the audit trail. See ADR-0021.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class EventCoordinatorAssignment(Base):
    """One immutable assignment-history entry for an event request."""

    __tablename__ = "event_coordinator_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    # Null for the first assignment: there was no previous owner.
    previous_coordinator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    new_coordinator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    acted_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
