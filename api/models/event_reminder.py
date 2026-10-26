"""A reminder the Coordinator asked for before their event (SCRUM-85).

One row per lead time per event, and the row *is* the occurrence: it carries both the
schedule ("an hour before") and whether that occurrence has been processed. Keeping the
two together is what makes AC6 cheap — "at most one reminder per event/configured
occurrence" is a single flag on a locked row rather than a separate ledger to reconcile.

It also makes AC8 fall out: moving the event moves the due time, because the due time is
derived from the event's start rather than stored, while anything already processed stays
processed. Recalculated future occurrences and retained history, without a second table.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class EventReminder(Base):
    __tablename__ = "event_reminders"
    __table_args__ = (
        # AC1: "positive whole minutes before its start". The domain refuses these too;
        # the constraint is here because a future caller is the easy way in.
        CheckConstraint("lead_minutes > 0", name="event_reminders_lead_minutes_positive"),
        # AC1: distinct lead times. The same reminder twice is not two reminders.
        UniqueConstraint("event_request_id", "lead_minutes", name="uq_event_reminder_lead"),
        # The sweep asks for unprocessed rows across every event, so the index matches
        # the order it reads them in rather than the order they were created.
        Index("ix_event_reminders_unprocessed", "processed_at", "event_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    #: Whole minutes before the event's start. The due time is derived, never stored, so
    #: a change to the event's time moves every future occurrence with it (AC8).
    lead_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: AC6 and AC7: when this occurrence was processed, whether or not that produced a
    #: reminder. Set even when nothing was outstanding, so a due occurrence cannot fire
    #: again on every tick for the rest of the event's life.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
