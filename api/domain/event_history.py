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
from itertools import pairwise

from domain.event_change import ChangeRequestStatus
from domain.event_clarification import ClarificationKind
from domain.event_replanning import ReplanCause
from domain.safety_review import SafetyDecision
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
    # SCRUM-119 equipment. A change to a requirement ranks before the reservation flags it
    # raises in the same instant, because the change is what raised them.
    REQUIREMENT_ADDED = "requirement_added"
    REQUIREMENT_UPDATED = "requirement_updated"
    REQUIREMENT_REMOVED = "requirement_removed"
    EQUIPMENT_RESERVED = "equipment_reserved"
    RESERVATION_FLAGGED = "reservation_flagged"
    RESERVATION_RELEASED = "reservation_released"
    # SCRUM-120 lifecycle. Appended, so every earlier pair keeps its order: at one instant
    # a hold's confirmation lists before the event's, and what a cause or a cancellation
    # changed lists before the event-level entry that links to it (ADR-0067).
    EVENT_CONFIRMED = "event_confirmed"
    RETURNED_TO_PLANNING = "returned_to_planning"
    EVENT_CANCELLED = "event_cancelled"
    # SCRUM-120 change requests and completion, appended after the lifecycle actions. At
    # one instant a return to planning lists before the decision that caused it, and links
    # to it (ADR-0068).
    CHANGE_REQUESTED = "change_requested"
    CHANGE_DECIDED = "change_decided"
    EVENT_COMPLETED = "event_completed"
    CLOSURE_CORRECTED = "closure_corrected"
    # SCRUM-120 safety decisions and venue closures, appended likewise (ADR-0069).
    SAFETY_DECIDED = "safety_decided"
    VENUE_CLOSED = "venue_closed"


class HistorySource(StrEnum):
    """Which kind of record an entry was read from. With `source_id` it names the row."""

    EVENT_REQUEST = "event_request"
    COORDINATOR_ASSIGNMENT = "coordinator_assignment"
    CLARIFICATION = "clarification"
    VENUE_BOOKING = "venue_booking"
    VENUE_BUFFER_CHANGE = "venue_buffer_change"
    EQUIPMENT_REQUIREMENT_CHANGE = "equipment_requirement_change"
    EQUIPMENT_RESERVATION = "equipment_reservation"
    # SCRUM-120: a return to planning is read from the approval it invalidated.
    SAFETY_REVIEW = "safety_review"
    EVENT_CHANGE_REQUEST = "event_change_request"
    EVENT_CLOSURE_NOTE = "event_closure_note"
    VENUE_CLOSURE_IMPACT = "venue_closure_impact"


class HistoryOutcome(StrEnum):
    """The result of a decision entry."""

    APPROVED = "approved"
    REJECTED = "rejected"
    # SCRUM-79: the Safety Officer sent the plan back as nearly there, not unsafe.
    CHANGES_REQUESTED = "changes_requested"


@dataclass(frozen=True)
class Person:
    """Someone named on a record. `email` is None when their user row is missing."""

    id: uuid.UUID
    email: str | None


class FieldKind(StrEnum):
    """How the UI shows a field change's values (ADR-0068)."""

    TEXT = "text"
    # A UTC ISO 8601 instant, shown in Singapore time by the UI, never converted here.
    DATETIME = "datetime"


@dataclass(frozen=True)
class FieldChange:
    """One value before and after an action, under the label the UI shows for it.

    Values are text so one renderer shows numbers and text alike; None is "no value", the
    old side of something added or the new side of something removed. `kind` says when
    the text is an instant the UI must show in local time (SCRUM-120, ADR-0068).
    """

    field: str
    label: str
    old: str | None
    new: str | None
    kind: FieldKind = FieldKind.TEXT


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
    # SCRUM-115: set once, together, when the event is cancelled.
    cancelled_by: Person | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    # SCRUM-86: set once, together, when the event is completed.
    completed_by: Person | None = None
    completed_at: datetime | None = None


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
class RequirementChangeRecord:
    """One `equipment_requirement_changes` row (SCRUM-43 AC8). `action` is the stored
    "added", "updated" or "removed"; an added row has no old values, a removed one no new."""

    id: uuid.UUID
    action: str
    equipment_type: str
    changed_by: Person
    changed_at: datetime
    old_quantity: int | None
    new_quantity: int | None
    old_technical_requirements: str | None
    new_technical_requirements: str | None


@dataclass(frozen=True)
class ReservationRecord:
    """One `equipment_reservations` row (SCRUM-53), with who reserved and who released it.
    The quantity stays on the row after a release, so what was held is still known."""

    id: uuid.UUID
    equipment_type: str
    quantity: int
    reserved_by: Person
    reserved_at: datetime
    flagged_at: datetime | None
    released_by: Person | None
    released_at: datetime | None


@dataclass(frozen=True)
class ChangeItemRecord:
    """One `event_change_items` row (SCRUM-37), as stored: the JSON current and proposed
    values. `subject` is the session label or equipment type it changes, read from that
    row when it exists; None for the event's own fields or when it is not found."""

    target: str
    field: str
    current: object
    proposed: object
    subject: str | None


@dataclass(frozen=True)
class ChangeRequestRecord:
    """One `event_change_requests` row (SCRUM-37/47) with its items in their order."""

    id: uuid.UUID
    requested_by: Person
    created_at: datetime
    reason: str
    status: str
    decided_by: Person | None
    decided_at: datetime | None
    decision_note: str | None
    items: tuple[ChangeItemRecord, ...]


@dataclass(frozen=True)
class ClosureNoteRecord:
    """One `event_closure_notes` version (SCRUM-86). Version 1 is written by completion."""

    id: uuid.UUID
    version: int
    actual_attendance: int | None
    notes: str | None
    recorded_by: Person
    recorded_at: datetime


@dataclass(frozen=True)
class SafetyDecisionRecord:
    """One `safety_reviews` row (SCRUM-79): a decision and the comment it was given with."""

    id: uuid.UUID
    decision: SafetyDecision
    comment: str
    decided_by: Person
    decided_at: datetime


@dataclass(frozen=True)
class ClosureImpactRecord:
    """One `venue_closure_impacts` row (SCRUM-81): a closure as it was saved, with only the
    affected arrangements that are this event's. Never changed after it is written."""

    id: uuid.UUID
    venue_name: str
    recorded_by: Person
    recorded_at: datetime
    starts_at: datetime
    ends_at: datetime
    reason: str
    affected_booking_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class ReplanRecord:
    """One `safety_reviews` approval that stopped counting because the event went back to
    planning (SCRUM-130). The return writes no row of its own; this marker is its only
    record, with the time and the cause but not who (ADR-0052, ADR-0067)."""

    id: uuid.UUID
    invalidated_at: datetime
    cause: ReplanCause


@dataclass(frozen=True)
class ReplanCauseRecord:
    """An action that can send an event back to planning, with who did it and when.

    `entry_key` is the history entry that action has, when it has one, so the return can
    link to it rather than repeat it."""

    cause: ReplanCause
    actor: Person
    at: datetime
    entry_key: str | None


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
    equipment_type: str | None = None
    quantity: int | None = None
    # SCRUM-120. False when the record keeps no actor for a person's action, which is not
    # the system: shown as "actor not recorded" rather than guessed (ADR-0067).
    actor_recorded: bool = True
    replan_cause: ReplanCause | None = None
    # The `key`s of other entries this one is about, so nothing is shown twice.
    related_entry_ids: tuple[str, ...] = ()
    # SCRUM-120: a closure's period, which is not a session's.
    period_start_at: datetime | None = None
    period_end_at: datetime | None = None

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


_REQUIREMENT_ACTIONS = {
    "added": HistoryAction.REQUIREMENT_ADDED,
    "updated": HistoryAction.REQUIREMENT_UPDATED,
    "removed": HistoryAction.REQUIREMENT_REMOVED,
}


def _text(value: int | None) -> str | None:
    return None if value is None else str(value)


def requirement_change_entry(record: RequirementChangeRecord) -> HistoryEntry:
    """An equipment requirement added, changed or removed, by the assigned Coordinator.

    Emits exactly quantity and technical requirements, both sides, as the row keeps them:
    an addition has no old values and a removal no new ones (ADR-0064). The requirement
    the organiser picked is carried across at approval with no change row (SCRUM-43), so
    it has no "added" entry (ADR-0065).
    """
    return HistoryEntry(
        _REQUIREMENT_ACTIONS[record.action],
        record.changed_at,
        record.changed_by,
        HistorySource.EQUIPMENT_REQUIREMENT_CHANGE,
        record.id,
        equipment_type=record.equipment_type,
        changes=(
            FieldChange(
                "quantity",
                "Quantity",
                _text(record.old_quantity),
                _text(record.new_quantity),
            ),
            FieldChange(
                "technical_requirements",
                "Technical requirements",
                record.old_technical_requirements,
                record.new_technical_requirements,
            ),
        ),
    )


def reservation_entries(record: ReservationRecord) -> list[HistoryEntry]:
    """A reservation made, flagged for reconsideration, and released, each with its
    quantity.

    A flag is set by the requirement change that made the reservation stop matching, in
    the same commit, and stores no actor, so it is the system's; only the first flag is
    kept (ADR-0033, ADR-0065). A release is recorded with who and when; today only a
    whole-event cancellation (SCRUM-115) releases.
    """

    def entry(action: HistoryAction, at: datetime, actor: Person | None) -> HistoryEntry:
        return HistoryEntry(
            action,
            at,
            actor,
            HistorySource.EQUIPMENT_RESERVATION,
            record.id,
            equipment_type=record.equipment_type,
            quantity=record.quantity,
        )

    entries = [entry(HistoryAction.EQUIPMENT_RESERVED, record.reserved_at, record.reserved_by)]
    if record.flagged_at is not None:
        entries.append(entry(HistoryAction.RESERVATION_FLAGGED, record.flagged_at, None))
    if record.released_at is not None:
        entries.append(
            entry(HistoryAction.RESERVATION_RELEASED, record.released_at, record.released_by)
        )
    return entries


def confirmation_entry(record: RequestRecord) -> HistoryEntry | None:
    """SCRUM-80: the event's confirmation, by the assigned Coordinator.

    `confirmed_by` / `confirmed_at` hold only the latest confirmation: confirming a
    replanned event again overwrites them, so an earlier confirmation is not shown. They
    are not cleared by a return to planning, so the last one stays (ADR-0062, ADR-0067).
    """
    if record.confirmed_at is None:
        return None
    return HistoryEntry(
        HistoryAction.EVENT_CONFIRMED,
        record.confirmed_at,
        record.confirmed_by,
        HistorySource.EVENT_REQUEST,
        record.id,
    )


def replan_entry(record: ReplanRecord, causes: Iterable[ReplanCauseRecord]) -> HistoryEntry:
    """SCRUM-130: the event went back to planning, when and why.

    The action that caused it is written in the same transaction, with the same time, so
    its actor is the return's: matched by cause and exact time, never by nearness. Unless
    exactly one action matches, no actor is shown and the entry says it was not recorded
    (ADR-0067). A matched action with an entry of its own is linked, not repeated.
    """
    matches = [c for c in causes if c.cause is record.cause and c.at == record.invalidated_at]
    entry = HistoryEntry(
        HistoryAction.RETURNED_TO_PLANNING,
        record.invalidated_at,
        None,
        HistorySource.SAFETY_REVIEW,
        record.id,
        actor_recorded=False,
        replan_cause=record.cause,
    )
    if len(matches) != 1:
        return entry
    [cause] = matches
    return replace(
        entry,
        actor=cause.actor,
        actor_recorded=True,
        related_entry_ids=() if cause.entry_key is None else (cause.entry_key,),
    )


def cancellation_entry(
    record: RequestRecord,
    bookings: Iterable[BookingRecord],
    reservations: Iterable[ReservationRecord],
) -> HistoryEntry | None:
    """SCRUM-115: the event's cancellation, once, with its reason, linked to what it released.

    The cancellation cancels each live arrangement and releases each reservation in its
    own transaction, stamping them with the event's actor and time. Those already have
    their own SCRUM-119 entries, so this one names them by `key` instead of repeating
    them: exactly the ones with the same actor and the same time (ADR-0067).
    """
    if record.cancelled_at is None:
        return None
    by, at = record.cancelled_by, record.cancelled_at
    released = [
        f"{HistoryAction.ARRANGEMENT_CANCELLED}:{b.id}"
        for b in bookings
        if b.cancelled_at == at and b.cancelled_by == by
    ] + [
        f"{HistoryAction.RESERVATION_RELEASED}:{r.id}"
        for r in reservations
        if r.released_at == at and r.released_by == by
    ]
    return HistoryEntry(
        HistoryAction.EVENT_CANCELLED,
        at,
        by,
        HistorySource.EVENT_REQUEST,
        record.id,
        reason=record.cancellation_reason,
        related_entry_ids=tuple(sorted(released)),
    )


# SCRUM-37: every value a change request can carry, as `target.field`, with its label
# and kind. An item outside this list is never shown (ADR-0064 rule 1). A session or
# equipment label is prefixed with what it changes.
_CHANGE_FIELDS: dict[str, tuple[str, FieldKind]] = {
    "event.start_at": ("Start date and time", FieldKind.DATETIME),
    "event.end_at": ("End date and time", FieldKind.DATETIME),
    "event.expected_attendance": ("Expected attendance", FieldKind.TEXT),
    "event.venue_requirement": ("Venue requirement", FieldKind.TEXT),
    "event.accessibility_requirement": ("Accessibility requirement", FieldKind.TEXT),
    "event.layout_requirement": ("Layout requirement", FieldKind.TEXT),
    "session.session_label": ("name", FieldKind.TEXT),
    "session.start_at": ("start", FieldKind.DATETIME),
    "session.end_at": ("end", FieldKind.DATETIME),
    "equipment.quantity": ("quantity", FieldKind.TEXT),
    "equipment.technical_requirements": ("technical requirements", FieldKind.TEXT),
    "equipment.add": ("line added", FieldKind.TEXT),
    "equipment.remove": ("line removed", FieldKind.TEXT),
}


def _change_value(value: object) -> str | None:
    """A stored JSON value as text. A whole equipment line reads "Projector × 2 (HDMI)"."""
    if value is None:
        return None
    if isinstance(value, dict):
        line = f"{value.get('equipment_type')} × {value.get('quantity')}"
        technical = value.get("technical_requirements")
        return line if technical is None else f"{line} ({technical})"
    return str(value)


def _change_label(item: ChangeItemRecord, label: str) -> str:
    if item.target == "session":
        return f"Session “{item.subject}”: {label}" if item.subject else f"A session: {label}"
    if item.target == "equipment":
        line = item.current if isinstance(item.current, dict) else item.proposed
        subject = line.get("equipment_type") if isinstance(line, dict) else item.subject
        return f"{subject or 'Equipment'}: {label}"
    return label


def change_request_entries(record: ChangeRequestRecord) -> list[HistoryEntry]:
    """SCRUM-37/47: the Organiser's request, with its reason and every item's old and new
    value, and the Coordinator's decision with its note.

    The values are on the request entry only, so they are shown once. Each item is emitted
    only if `target.field` is whitelisted, under its label; dates keep their stored UTC
    text and are marked DATETIME so the UI shows them in local time (ADR-0068).
    """
    changes = tuple(
        FieldChange(
            key,
            _change_label(item, _CHANGE_FIELDS[key][0]),
            _change_value(item.current),
            _change_value(item.proposed),
            _CHANGE_FIELDS[key][1],
        )
        for item in record.items
        if (key := f"{item.target}.{item.field}") in _CHANGE_FIELDS
    )
    entries = [
        HistoryEntry(
            HistoryAction.CHANGE_REQUESTED,
            record.created_at,
            record.requested_by,
            HistorySource.EVENT_CHANGE_REQUEST,
            record.id,
            reason=record.reason,
            changes=changes,
        )
    ]
    if record.decided_at is not None:
        approved = record.status == ChangeRequestStatus.APPROVED
        entries.append(
            HistoryEntry(
                HistoryAction.CHANGE_DECIDED,
                record.decided_at,
                record.decided_by,
                HistorySource.EVENT_CHANGE_REQUEST,
                record.id,
                outcome=HistoryOutcome.APPROVED if approved else HistoryOutcome.REJECTED,
                reason=record.decision_note,
            )
        )
    return entries


def _closure_changes(
    old: ClosureNoteRecord | None, new: ClosureNoteRecord
) -> tuple[FieldChange, ...]:
    """Exactly attendance and notes, both sides, whether or not each moved."""
    return (
        FieldChange(
            "actual_attendance",
            "Actual attendance",
            None if old is None else _text(old.actual_attendance),
            _text(new.actual_attendance),
        ),
        FieldChange(
            "notes",
            "Operational notes and issues",
            None if old is None else old.notes,
            new.notes,
        ),
    )


def completion_entries(
    record: RequestRecord, notes: Iterable[ClosureNoteRecord]
) -> list[HistoryEntry]:
    """SCRUM-86: the completion, carrying the closure record it wrote (version 1), and
    each later correction against the version before it.

    Completion writes version 1 in the same transaction, so its values belong to the
    completion entry rather than a second one. Every version is kept (ADR-0059), so
    each correction's old values are the previous version's, not reconstructed.
    """
    versions = sorted(notes, key=lambda n: n.version)
    entries = []
    if record.completed_at is not None:
        first = next((n for n in versions if n.version == 1), None)
        entries.append(
            HistoryEntry(
                HistoryAction.EVENT_COMPLETED,
                record.completed_at,
                record.completed_by,
                HistorySource.EVENT_REQUEST,
                record.id,
                changes=() if first is None else _closure_changes(None, first),
            )
        )
    for previous, note in pairwise(versions):
        entries.append(
            HistoryEntry(
                HistoryAction.CLOSURE_CORRECTED,
                note.recorded_at,
                note.recorded_by,
                HistorySource.EVENT_CLOSURE_NOTE,
                note.id,
                changes=_closure_changes(previous, note),
            )
        )
    return entries


_SAFETY_OUTCOMES = {
    SafetyDecision.APPROVE: HistoryOutcome.APPROVED,
    SafetyDecision.REJECT: HistoryOutcome.REJECTED,
    SafetyDecision.REQUEST_CHANGES: HistoryOutcome.CHANGES_REQUESTED,
}


def safety_decision_entry(record: SafetyDecisionRecord) -> HistoryEntry:
    """SCRUM-79: a Safety Officer's decision with its comment. Every decision is its own
    row and never edited, so each is shown. Who may see it is `visible`'s question: the
    owner may not (ADR-0069). That an approval later stopped counting is the return to
    planning's entry, not this one's."""
    return HistoryEntry(
        HistoryAction.SAFETY_DECIDED,
        record.decided_at,
        record.decided_by,
        HistorySource.SAFETY_REVIEW,
        record.id,
        outcome=_SAFETY_OUTCOMES[record.decision],
        reason=record.comment,
    )


def closure_impact_entry(record: ClosureImpactRecord) -> HistoryEntry:
    """SCRUM-81: a venue closure saved over this event's arrangements, by Venue Staff, with
    the period and reason as they were then. Each save that hit one is its own row."""
    return HistoryEntry(
        HistoryAction.VENUE_CLOSED,
        record.recorded_at,
        record.recorded_by,
        HistorySource.VENUE_CLOSURE_IMPACT,
        record.id,
        venue_name=record.venue_name,
        reason=record.reason,
        affected_booking_ids=record.affected_booking_ids,
        period_start_at=record.starts_at,
        period_end_at=record.ends_at,
    )


def _closure_causes(impacts: Iterable[ClosureImpactRecord]) -> list[ReplanCauseRecord]:
    """SCRUM-132: a closure saved in the same transaction as a return to planning caused
    it; its entry is linked (ADR-0069)."""
    return [
        ReplanCauseRecord(
            ReplanCause.VENUE_CLOSURE,
            i.recorded_by,
            i.recorded_at,
            f"{HistoryAction.VENUE_CLOSED}:{i.id}",
        )
        for i in impacts
    ]


def _booking_causes(bookings: Iterable[BookingRecord]) -> list[ReplanCauseRecord]:
    """SCRUM-118: every cancelled arrangement could be a venue change; only one cancelled
    in the same transaction as a return to planning will match it."""
    return [
        ReplanCauseRecord(
            ReplanCause.VENUE_CANCELLATION,
            b.cancelled_by,
            b.cancelled_at,
            f"{HistoryAction.ARRANGEMENT_CANCELLED}:{b.id}",
        )
        for b in bookings
        if b.cancelled_by is not None and b.cancelled_at is not None
    ]


def visible(
    entries: Iterable[HistoryEntry],
    may_read_clarifications: bool,
    may_read_safety_reviews: bool = False,
) -> list[HistoryEntry]:
    """SCRUM-106: note entries only for a viewer who may read the notes. Anyone else gets
    no trace of them, not even an entry without its text (ADR-0036).

    SCRUM-120: safety decision entries likewise, only for a viewer who may read safety
    decisions (ADR-0069). A return to planning is not a decision and stays."""
    return [
        entry
        for entry in entries
        if (may_read_clarifications or entry.source_type is not HistorySource.CLARIFICATION)
        and (may_read_safety_reviews or entry.action is not HistoryAction.SAFETY_DECIDED)
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
    requirement_changes: Iterable[RequirementChangeRecord] = (),
    reservations: Iterable[ReservationRecord] = (),
    replans: Iterable[ReplanRecord] = (),
    replan_causes: Iterable[ReplanCauseRecord] = (),
    change_requests: Iterable[ChangeRequestRecord] = (),
    closure_notes: Iterable[ClosureNoteRecord] = (),
    safety_decisions: Iterable[SafetyDecisionRecord] = (),
    closure_impacts: Iterable[ClosureImpactRecord] = (),
    *,
    may_read_safety_reviews: bool = False,
) -> list[HistoryEntry]:
    """Every reader's entries for one event, filtered for the viewer, oldest first.

    `replan_causes` are the change-request decisions; venue changes and closures among the
    causes are read from `bookings` and `closure_impacts`, which are already here."""
    bookings = list(bookings)
    reservations = list(reservations)
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
    entries += [requirement_change_entry(c) for c in requirement_changes]
    for reservation in reservations:
        entries += reservation_entries(reservation)
    closure_impacts = list(closure_impacts)
    causes = _booking_causes(bookings) + _closure_causes(closure_impacts) + list(replan_causes)
    entries += [replan_entry(r, causes) for r in replans]
    entries += [
        e
        for e in (
            confirmation_entry(request),
            cancellation_entry(request, bookings, reservations),
        )
        if e is not None
    ]
    for change in change_requests:
        entries += change_request_entries(change)
    entries += completion_entries(request, closure_notes)
    entries += [safety_decision_entry(d) for d in safety_decisions]
    entries += [closure_impact_entry(i) for i in closure_impacts]
    return ordered(visible(entries, may_read_clarifications, may_read_safety_reviews))
