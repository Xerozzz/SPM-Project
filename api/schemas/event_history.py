"""API contract for an event's history (SCRUM-88, ADR-0062)."""

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel

from domain.event_history import HistoryAction, HistoryEntry, HistoryOutcome, HistorySource


class EventHistoryEntryRead(BaseModel):
    """One recorded action, oldest first. The UI shows exactly these fields (AC9).

    `actor_id` and `actor_email` are both None for the system (a hold's expiry); an
    `actor_email` alone is None when the user row is missing ("Unknown user"). The fields
    after `reason` are set only on the entries they describe, and `note` only on a
    clarification entry, which only the event's current assigned Coordinator receives.
    """

    id: str
    action: HistoryAction
    occurred_at: datetime
    actor_id: uuid.UUID | None
    actor_email: str | None
    source_type: HistorySource
    source_id: uuid.UUID
    outcome: HistoryOutcome | None
    reason: str | None
    previous_coordinator_email: str | None
    new_coordinator_email: str | None
    venue_name: str | None
    session_label: str | None
    hold_expires_at: datetime | None
    note: str | None

    @classmethod
    def from_entry(cls, entry: HistoryEntry) -> Self:
        return cls(
            id=entry.key,
            action=entry.action,
            occurred_at=entry.occurred_at,
            actor_id=None if entry.actor is None else entry.actor.id,
            actor_email=None if entry.actor is None else entry.actor.email,
            source_type=entry.source_type,
            source_id=entry.source_id,
            outcome=entry.outcome,
            reason=entry.reason,
            previous_coordinator_email=entry.previous_coordinator_email,
            new_coordinator_email=entry.new_coordinator_email,
            venue_name=entry.venue_name,
            session_label=entry.session_label,
            hold_expires_at=entry.hold_expires_at,
            note=entry.note,
        )
