"""API contract for an event's history (SCRUM-88, ADR-0062)."""

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel

from domain.event_history import (
    FieldKind,
    HistoryAction,
    HistoryEntry,
    HistoryOutcome,
    HistorySource,
)
from domain.event_replanning import ReplanCause


class FieldChangeRead(BaseModel):
    """SCRUM-119: one value before and after, with the label to show for it (ADR-0064).
    Only fields a reader names are ever sent; None is "no value"."""

    field: str
    label: str
    old: str | None
    new: str | None
    # SCRUM-120: "datetime" when the values are UTC instants to show in local time.
    kind: FieldKind


class EventHistoryEntryRead(BaseModel):
    """One recorded action, oldest first. The UI shows exactly these fields (AC9).

    `actor_id` and `actor_email` are both None for the system (a hold's expiry); an
    `actor_email` alone is None when the user row is missing ("Unknown user"). The fields
    after `reason` are set only on the entries they describe, and `note` only on a
    clarification entry, which only the event's current assigned Coordinator receives.

    SCRUM-119 adds the session period to venue entries, the other arrangement of a
    replacement, the bookings a buffer change caught out, and before-and-after `changes`,
    and to equipment entries their equipment type and, for a reservation, its quantity.

    SCRUM-120: `actor_recorded` is False when a person acted but the record keeps no
    actor ("actor not recorded", not the system); `replan_cause` says why an event went
    back to planning; `related_entry_ids` are the `id`s of the entries an event-level
    entry links to, which are not repeated in it (ADR-0067). `period_start_at` and
    `period_end_at` are a venue closure's period (ADR-0069).
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
    session_start_at: datetime | None
    session_end_at: datetime | None
    related_booking_id: uuid.UUID | None
    affected_booking_ids: list[uuid.UUID]
    changes: list[FieldChangeRead]
    equipment_type: str | None
    quantity: int | None
    actor_recorded: bool
    replan_cause: ReplanCause | None
    related_entry_ids: list[str]
    period_start_at: datetime | None
    period_end_at: datetime | None

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
            session_start_at=entry.session_start_at,
            session_end_at=entry.session_end_at,
            related_booking_id=entry.related_booking_id,
            affected_booking_ids=list(entry.affected_booking_ids),
            changes=[
                FieldChangeRead(field=c.field, label=c.label, old=c.old, new=c.new, kind=c.kind)
                for c in entry.changes
            ],
            equipment_type=entry.equipment_type,
            quantity=entry.quantity,
            actor_recorded=entry.actor_recorded,
            replan_cause=entry.replan_cause,
            related_entry_ids=list(entry.related_entry_ids),
            period_start_at=entry.period_start_at,
            period_end_at=entry.period_end_at,
        )
