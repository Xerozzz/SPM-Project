"""One event's history, read from the records each story already keeps (SCRUM-88). Pure.

There is no history table (ADR-0062). Each source record is turned into the entries it
can vouch for by one small reader below, and `timeline` puts them in one order. A later
story adds a source by adding a reader, without changing the timeline (SCRUM-119/120).

A reader only reports what its record says. Where a record keeps no actor or no separate
time for an action, the entry says so (a None actor is the system) or the entry is not
made; nothing is reconstructed. The gaps are listed in ADR-0062 and ADR-0064.

Before-and-after values travel as `FieldChange`s. Each reader names the fields it emits,
and their labels, itself: none copies a row or compares every column, so a field nobody
chose can never reach the history (ADR-0064).
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from domain.event_clarification import ClarificationKind
from domain.venue_booking import BookingStatus


class HistoryAction(StrEnum):
    """What an entry records. Declaration order is the tie-breaker for equal times, so it
    follows the order things happen in: a request is created before it is submitted, and
    a hold is created before it is confirmed or expires."""

    DRAFT_CREATED = "draft_created"
    SUBMITTED = "submitted"
    REVIEW_DECIDED = "review_decided"
    COORDINATOR_ASSIGNED = "coordinator_assigned"
    COORDINATOR_REASSIGNED = "coordinator_reassigned"
    CLARIFICATION_REQUESTED = "clarification_requested"
    # Written only by the superseded SCRUM-30 exchange; old rows still read back.
    CLARIFICATION_RESPONDED = "clarification_responded"
    VENUE_REQUESTED = "venue_requested"
    VENUE_DECIDED = "venue_decided"
    HOLD_CREATED = "hold_created"
    HOLD_CONFIRMED = "hold_confirmed"
    HOLD_EXPIRED = "hold_expired"
    # SCRUM-119. Added after the SCRUM-88 actions so their order among themselves stays;
    # adopting ranks before cancelling because adoption is what cancels the original.
    REPLACEMENT_ADOPTED = "replacement_adopted"
    ARRANGEMENT_CANCELLED = "arrangement_cancelled"
    BUFFER_CHANGED = "buffer_changed"


class HistorySource(StrEnum):
    """Which kind of record an entry was read from. With `source_id` it names the row."""

    EVENT_REQUEST = "event_request"
    COORDINATOR_ASSIGNMENT = "coordinator_assignment"
    CLARIFICATION = "clarification"
    VENUE_BOOKING = "venue_booking"
    VENUE_BUFFER_CHANGE = "venue_buffer_change"


class HistoryOutcome(StrEnum):
    """The result of a decision entry."""

    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Person:
    """Someone named on a record. `email` is None when their user row is missing."""

    id: uuid.UUID
    email: str | None


@dataclass(frozen=True)
class FieldChange:
    """One value before and after an action, under the label the UI shows for it.

    Values are text so one renderer shows numbers and text alike; None is "no value", the
    old side of something added or the new side of something removed.
    """

    field: str
    label: str
    old: str | None
    new: str | None


@dataclass(frozen=True)
class RequestRecord:
    """The milestone columns of `event_requests`. Each holds only its latest value."""

    id: uuid.UUID
    owner: Person
    created_at: datetime
    submitted_at: datetime | None
    decided_by: Person | None
    decided_at: datetime | None
    rejection_reason: str | None
    confirmed_by: Person | None
    confirmed_at: datetime | None


@dataclass(frozen=True)
class AssignmentRecord:
    """One `event_coordinator_assignments` row (SCRUM-97, ADR-0021)."""

    id: uuid.UUID
    previous: Person | None
    new: Person
    acted_by: Person
    assigned_at: datetime


@dataclass(frozen=True)
class ClarificationRecord:
    """One `event_clarifications` row (SCRUM-106)."""

    id: uuid.UUID
    author: Person
    kind: ClarificationKind
    message: str
    created_at: datetime


@dataclass(frozen=True)
class BookingRecord:
    """One `venue_bookings` row with its venue's name."""

    id: uuid.UUID
    status: BookingStatus
    venue_name: str
    session_label: str
    start_at: datetime
    end_at: datetime
    requested_by: Person
    created_at: datetime
    decided_by: Person | None
    decided_at: datetime | None
    decision_reason: str | None
    held_by: Person | None
    held_at: datetime | None
    expires_at: datetime | None
    cancelled_by: Person | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    # SCRUM-116: the arrangement this request would replace, kept after either is decided.
    replaces_booking_id: uuid.UUID | None
    adopted_by: Person | None
    adopted_at: datetime | None


@dataclass(frozen=True)
class BufferChangeRecord:
    """One `venue_buffer_changes` row (SCRUM-89), with only the flagged bookings that are
    this event's. The flags are what the change made problematic when it was saved."""

    id: uuid.UUID
    venue_name: str
    changed_by: Person
    changed_at: datetime
    old_setup_minutes: int
    old_turnaround_minutes: int
    new_setup_minutes: int
    new_turnaround_minutes: int
    affected_booking_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class HistoryEntry:
    """One action in the history. A None `actor` is the system (a hold's expiry)."""

    action: HistoryAction
    occurred_at: datetime
    actor: Person | None
    source_type: HistorySource
    source_id: uuid.UUID
    outcome: HistoryOutcome | None = None
    reason: str | None = None
    previous_coordinator_email: str | None = None
    new_coordinator_email: str | None = None
    venue_name: str | None = None
    session_label: str | None = None
    hold_expires_at: datetime | None = None
    note: str | None = None
    session_start_at: datetime | None = None
    session_end_at: datetime | None = None
    # The other arrangement in a replacement: the one replaced, or the one replacing it.
    related_booking_id: uuid.UUID | None = None
    affected_booking_ids: tuple[uuid.UUID, ...] = ()
    changes: tuple[FieldChange, ...] = ()

    @property
    def key(self) -> str:
        """Unique within one history: a record yields each action at most once."""
        return f"{self.action}:{self.source_id}"


def request_entries(record: RequestRecord) -> list[HistoryEntry]:
    """Creation, submission and the Coordinator's decision.

    Only the owner creates or submits, so they are the actor of both. A resubmission
    overwrites `submitted_at`, and a later decision overwrites the earlier one and clears
    its reason, so only the latest submission and decision can be shown (ADR-0062).
    """

    def entry(action: HistoryAction, at: datetime, actor: Person | None) -> HistoryEntry:
        return HistoryEntry(action, at, actor, HistorySource.EVENT_REQUEST, record.id)

    entries = [entry(HistoryAction.DRAFT_CREATED, record.created_at, record.owner)]
    if record.submitted_at is not None:
        entries.append(entry(HistoryAction.SUBMITTED, record.submitted_at, record.owner))
    if record.decided_at is not None:
        # Rejecting always stores a reason and approving always clears it.
        rejected = record.rejection_reason is not None
        entries.append(
            replace(
                entry(HistoryAction.REVIEW_DECIDED, record.decided_at, record.decided_by),
                outcome=HistoryOutcome.REJECTED if rejected else HistoryOutcome.APPROVED,
                reason=record.rejection_reason,
            )
        )
    return entries


def assignment_entry(record: AssignmentRecord) -> HistoryEntry:
    """A first assignment (no previous Coordinator) or a reassignment, by the Lead."""
    first = record.previous is None
    return HistoryEntry(
        HistoryAction.COORDINATOR_ASSIGNED if first else HistoryAction.COORDINATOR_REASSIGNED,
        record.assigned_at,
        record.acted_by,
        HistorySource.COORDINATOR_ASSIGNMENT,
        record.id,
        previous_coordinator_email=None if record.previous is None else record.previous.email,
        new_coordinator_email=record.new.email,
    )


def clarification_entry(record: ClarificationRecord) -> HistoryEntry:
    """One note, with its text. Who may see it is `visible`'s question, not this one's."""
    responded = record.kind is ClarificationKind.RESPONSE
    return HistoryEntry(
        HistoryAction.CLARIFICATION_RESPONDED
        if responded
        else HistoryAction.CLARIFICATION_REQUESTED,
        record.created_at,
        record.author,
        HistorySource.CLARIFICATION,
        record.id,
        note=record.message,
    )


def booking_entries(
    record: BookingRecord,
    confirmed_by: Person | None,
    confirmed_at: datetime | None,
    adopted_replacement_id: uuid.UUID | None = None,
) -> list[HistoryEntry]:
    """The request, the Venue Staff decision or hold, how the hold ended, and (SCRUM-119)
    its cancellation and, for a replacement, its adoption. Every entry carries the session
    label and period (AC4).

    Since SCRUM-110 approving a request is placing its hold, and only `held_*` is written,
    so that one action is one HOLD_CREATED entry. A decision entry comes from `decided_*`:
    a rejection, or an old SCRUM-74 approval that confirmed the booking directly.

    A booking keeps no record of its own confirmation, so a held booking that is now
    Confirmed takes the event's confirmation (`confirmed_by`, `confirmed_at`). Those are
    overwritten when a replanned event is confirmed again, so a booking confirmed the
    first time then shows the later confirmation (ADR-0062). An expiry has no actor, and
    its time is the hold's expiry, when it stopped holding the venue.

    A request that replaces another, and its adoption, name the original. Adoption cancels
    the original through SCRUM-109, so the original has its own cancellation entry, which
    names the adopted replacement given as `adopted_replacement_id` (ADR-0064). Every
    cancellation is shown with its reason, including those a whole-event cancellation
    (SCRUM-115) made. An update to a hold's expiry keeps no record, so it has no entry,
    and the hold entry shows the expiry as it is now (ADR-0064).
    """

    def entry(action: HistoryAction, at: datetime, actor: Person | None) -> HistoryEntry:
        return HistoryEntry(
            action,
            at,
            actor,
            HistorySource.VENUE_BOOKING,
            record.id,
            venue_name=record.venue_name,
            session_label=record.session_label,
            session_start_at=record.start_at,
            session_end_at=record.end_at,
        )

    entries = [
        replace(
            entry(HistoryAction.VENUE_REQUESTED, record.created_at, record.requested_by),
            related_booking_id=record.replaces_booking_id,
        )
    ]
    if record.decided_at is not None:
        rejected = record.status is BookingStatus.REJECTED
        entries.append(
            replace(
                entry(HistoryAction.VENUE_DECIDED, record.decided_at, record.decided_by),
                outcome=HistoryOutcome.REJECTED if rejected else HistoryOutcome.APPROVED,
                reason=record.decision_reason,
            )
        )
    if record.held_at is not None:
        entries.append(
            replace(
                entry(HistoryAction.HOLD_CREATED, record.held_at, record.held_by),
                hold_expires_at=record.expires_at,
            )
        )
        if record.status is BookingStatus.CONFIRMED and confirmed_at is not None:
            entries.append(entry(HistoryAction.HOLD_CONFIRMED, confirmed_at, confirmed_by))
    if record.status is BookingStatus.EXPIRED and record.expires_at is not None:
        entries.append(entry(HistoryAction.HOLD_EXPIRED, record.expires_at, None))
    if record.adopted_at is not None:
        entries.append(
            replace(
                entry(HistoryAction.REPLACEMENT_ADOPTED, record.adopted_at, record.adopted_by),
                related_booking_id=record.replaces_booking_id,
            )
        )
    if record.cancelled_at is not None:
        entries.append(
            replace(
                entry(
                    HistoryAction.ARRANGEMENT_CANCELLED, record.cancelled_at, record.cancelled_by
                ),
                reason=record.cancellation_reason,
                related_booking_id=adopted_replacement_id,
            )
        )
    return entries


def buffer_change_entry(record: BufferChangeRecord) -> HistoryEntry:
    """A venue's setup or turnaround changed and caught out this event's bookings.

    Emits exactly the two buffer fields, both sides, whether or not each one moved: the
    pair is what the venue's occupied interval is built from (ADR-0019).
    """
    return HistoryEntry(
        HistoryAction.BUFFER_CHANGED,
        record.changed_at,
        record.changed_by,
        HistorySource.VENUE_BUFFER_CHANGE,
        record.id,
        venue_name=record.venue_name,
        affected_booking_ids=record.affected_booking_ids,
        changes=(
            FieldChange(
                "setup_minutes",
                "Setup time (minutes)",
                str(record.old_setup_minutes),
                str(record.new_setup_minutes),
            ),
            FieldChange(
                "turnaround_minutes",
                "Turnaround time (minutes)",
                str(record.old_turnaround_minutes),
                str(record.new_turnaround_minutes),
            ),
        ),
    )


def visible(entries: Iterable[HistoryEntry], may_read_clarifications: bool) -> list[HistoryEntry]:
    """SCRUM-106: note entries only for a viewer who may read the notes. Anyone else gets
    no trace of them, not even an entry without its text (ADR-0036)."""
    return [
        entry
        for entry in entries
        if may_read_clarifications or entry.source_type is not HistorySource.CLARIFICATION
    ]


_RANK = {action: rank for rank, action in enumerate(HistoryAction)}


def ordered(entries: Iterable[HistoryEntry]) -> list[HistoryEntry]:
    """Oldest first. Equal times fall back to the action's rank, then the record's id, and
    `key` is unique, so the same records always come out in the same order."""
    return sorted(entries, key=lambda e: (e.occurred_at, _RANK[e.action], str(e.source_id)))


def timeline(
    request: RequestRecord,
    assignments: Iterable[AssignmentRecord],
    clarifications: Iterable[ClarificationRecord],
    bookings: Iterable[BookingRecord],
    may_read_clarifications: bool,
    buffer_changes: Iterable[BufferChangeRecord] = (),
) -> list[HistoryEntry]:
    """Every reader's entries for one event, filtered for the viewer, oldest first."""
    bookings = list(bookings)
    # The other side of each adoption, read from the replacement's own link.
    adopted = {
        b.replaces_booking_id: b.id
        for b in bookings
        if b.adopted_at is not None and b.replaces_booking_id is not None
    }
    entries = request_entries(request)
    entries += [assignment_entry(a) for a in assignments]
    entries += [clarification_entry(c) for c in clarifications]
    for booking in bookings:
        entries += booking_entries(
            booking, request.confirmed_by, request.confirmed_at, adopted.get(booking.id)
        )
    entries += [buffer_change_entry(c) for c in buffer_changes]
    return ordered(visible(entries, may_read_clarifications))
