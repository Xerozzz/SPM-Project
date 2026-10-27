"""SCRUM-88: the pure readers that turn source records into one event history."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from domain.event_clarification import ClarificationKind
from domain.event_history import (
    AssignmentRecord,
    BookingRecord,
    ClarificationRecord,
    HistoryAction,
    HistoryEntry,
    HistoryOutcome,
    HistorySource,
    Person,
    RequestRecord,
    assignment_entry,
    booking_entries,
    clarification_entry,
    ordered,
    request_entries,
    timeline,
    visible,
)
from domain.venue_booking import BookingStatus

T0 = datetime(2030, 1, 6, 9, tzinfo=UTC)
OWNER = Person(uuid.uuid4(), "owner@example.com")
COORDINATOR = Person(uuid.uuid4(), "coordinator@example.com")
LEAD = Person(uuid.uuid4(), "lead@example.com")
STAFF = Person(uuid.uuid4(), "staff@example.com")


def at(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def request(**overrides: Any) -> RequestRecord:
    """A draft; pass field=value to move it on."""
    draft = RequestRecord(uuid.uuid4(), OWNER, at(0), None, None, None, None, None, None)
    return replace(draft, **overrides)


def booking(**overrides: Any) -> BookingRecord:
    """A pending venue request; pass field=value to move it on."""
    pending = BookingRecord(
        id=uuid.uuid4(),
        status=BookingStatus.PENDING,
        venue_name="Hall A",
        session_label="Main session",
        requested_by=COORDINATOR,
        created_at=at(5),
        decided_by=None,
        decided_at=None,
        decision_reason=None,
        held_by=None,
        held_at=None,
        expires_at=None,
        # SCRUM-119 fields, empty for a plain pending request.
        start_at=at(100),
        end_at=at(102),
        cancelled_by=None,
        cancelled_at=None,
        cancellation_reason=None,
        replaces_booking_id=None,
        adopted_by=None,
        adopted_at=None,
    )
    return replace(pending, **overrides)


def note(
    kind: ClarificationKind = ClarificationKind.REQUEST, hours: float = 3
) -> ClarificationRecord:
    return ClarificationRecord(uuid.uuid4(), COORDINATOR, kind, "Check the fire exits", at(hours))


def actions(entries: list[HistoryEntry]) -> list[HistoryAction]:
    return [e.action for e in entries]


# --------------------------------------------------------------------- request reader


@pytest.mark.story("SCRUM-88")
def test_a_draft_has_only_its_creation_by_the_owner() -> None:
    record = request()

    [entry] = request_entries(record)

    assert entry.action is HistoryAction.DRAFT_CREATED
    assert (entry.occurred_at, entry.actor) == (at(0), OWNER)
    assert (entry.source_type, entry.source_id) == (HistorySource.EVENT_REQUEST, record.id)


@pytest.mark.story("SCRUM-88")
def test_submission_is_the_owners_and_an_approval_has_no_reason() -> None:
    record = request(submitted_at=at(1), decided_by=COORDINATOR, decided_at=at(2))

    created, submitted, decided = request_entries(record)

    assert (submitted.action, submitted.occurred_at, submitted.actor) == (
        HistoryAction.SUBMITTED,
        at(1),
        OWNER,
    )
    assert decided.action is HistoryAction.REVIEW_DECIDED
    assert (decided.actor, decided.outcome, decided.reason) == (
        COORDINATOR,
        HistoryOutcome.APPROVED,
        None,
    )


@pytest.mark.story("SCRUM-88")
def test_a_rejection_carries_its_reason() -> None:
    record = request(
        submitted_at=at(1), decided_by=COORDINATOR, decided_at=at(2), rejection_reason="Too big"
    )

    decided = request_entries(record)[-1]

    assert (decided.outcome, decided.reason) == (HistoryOutcome.REJECTED, "Too big")


@pytest.mark.story("SCRUM-88")
def test_a_resubmission_shows_only_the_latest_submission_and_decision() -> None:
    """ADR-0062 gap, pinned: rejected at 2h, resubmitted at 3h and approved at 4h leaves
    the columns holding only 3h and the approval, so the rejection is not shown."""
    record = request(submitted_at=at(3), decided_by=COORDINATOR, decided_at=at(4))

    entries = request_entries(record)

    assert actions(entries) == [
        HistoryAction.DRAFT_CREATED,
        HistoryAction.SUBMITTED,
        HistoryAction.REVIEW_DECIDED,
    ]
    assert entries[1].occurred_at == at(3)
    assert entries[2].outcome is HistoryOutcome.APPROVED


@pytest.mark.story("SCRUM-88")
def test_a_missing_decider_row_keeps_the_entry_without_an_email() -> None:
    record = request(decided_by=Person(COORDINATOR.id, None), decided_at=at(2))

    assert request_entries(record)[-1].actor == Person(COORDINATOR.id, None)


# ------------------------------------------------------------------ assignment reader


@pytest.mark.story("SCRUM-88")
def test_first_assignment_and_reassignment_name_the_lead_and_both_coordinators() -> None:
    other = Person(uuid.uuid4(), "other@example.com")
    first = assignment_entry(AssignmentRecord(uuid.uuid4(), None, COORDINATOR, LEAD, at(1)))
    second = assignment_entry(AssignmentRecord(uuid.uuid4(), COORDINATOR, other, LEAD, at(2)))

    assert first.action is HistoryAction.COORDINATOR_ASSIGNED
    assert (first.actor, first.previous_coordinator_email, first.new_coordinator_email) == (
        LEAD,
        None,
        COORDINATOR.email,
    )
    assert second.action is HistoryAction.COORDINATOR_REASSIGNED
    assert (second.previous_coordinator_email, second.new_coordinator_email) == (
        COORDINATOR.email,
        other.email,
    )
    assert second.source_type is HistorySource.COORDINATOR_ASSIGNMENT


# --------------------------------------------------------------- clarification reader


@pytest.mark.story("SCRUM-88")
def test_a_note_carries_its_author_and_text() -> None:
    record = note()

    entry = clarification_entry(record)

    assert entry.action is HistoryAction.CLARIFICATION_REQUESTED
    assert (entry.actor, entry.note, entry.occurred_at) == (COORDINATOR, record.message, at(3))
    assert entry.source_type is HistorySource.CLARIFICATION


@pytest.mark.story("SCRUM-88")
def test_a_legacy_response_reads_back_as_a_response() -> None:
    entry = clarification_entry(note(ClarificationKind.RESPONSE))

    assert entry.action is HistoryAction.CLARIFICATION_RESPONDED


# --------------------------------------------------------------------- booking reader


@pytest.mark.story("SCRUM-88")
def test_a_pending_request_is_one_entry_with_its_venue_and_session() -> None:
    [entry] = booking_entries(booking(), None, None)

    assert entry.action is HistoryAction.VENUE_REQUESTED
    assert (entry.actor, entry.venue_name, entry.session_label) == (
        COORDINATOR,
        "Hall A",
        "Main session",
    )


@pytest.mark.story("SCRUM-88")
def test_a_rejection_by_venue_staff_carries_its_reason() -> None:
    record = booking(
        status=BookingStatus.REJECTED,
        decided_by=STAFF,
        decided_at=at(6),
        decision_reason="Closed for works",
    )

    _, decided = booking_entries(record, None, None)

    assert decided.action is HistoryAction.VENUE_DECIDED
    assert (decided.actor, decided.outcome, decided.reason) == (
        STAFF,
        HistoryOutcome.REJECTED,
        "Closed for works",
    )


@pytest.mark.story("SCRUM-88")
def test_approval_is_the_hold_so_it_is_one_hold_entry() -> None:
    """SCRUM-110: approving writes only `held_*`, so one action gives one entry."""
    record = booking(
        status=BookingStatus.TENTATIVE, held_by=STAFF, held_at=at(6), expires_at=at(30)
    )

    entries = booking_entries(record, None, None)

    assert actions(entries) == [HistoryAction.VENUE_REQUESTED, HistoryAction.HOLD_CREATED]
    assert (entries[1].actor, entries[1].hold_expires_at) == (STAFF, at(30))


@pytest.mark.story("SCRUM-88")
@pytest.mark.parametrize("status", [BookingStatus.CONFIRMED, BookingStatus.CANCELLED])
def test_a_direct_scrum_74_confirmation_is_an_approval_decision(status: BookingStatus) -> None:
    record = booking(status=status, decided_by=STAFF, decided_at=at(6))

    decided = booking_entries(record, COORDINATOR, at(9))[-1]

    assert decided.action is HistoryAction.VENUE_DECIDED
    assert decided.outcome is HistoryOutcome.APPROVED


@pytest.mark.story("SCRUM-88")
def test_a_confirmed_hold_takes_the_events_confirmation() -> None:
    record = booking(
        status=BookingStatus.CONFIRMED, held_by=STAFF, held_at=at(6), expires_at=at(30)
    )

    confirmed = booking_entries(record, COORDINATOR, at(9))[-1]

    assert confirmed.action is HistoryAction.HOLD_CONFIRMED
    assert (confirmed.actor, confirmed.occurred_at) == (COORDINATOR, at(9))


@pytest.mark.story("SCRUM-88")
def test_re_confirmation_dates_every_confirmed_hold_from_the_latest_confirmation() -> None:
    """ADR-0062 gap, pinned: a hold confirmed at 9h, a replan, a second hold, and a
    re-confirmation at 20h leave only 20h on the event, so both holds show 20h."""
    first = booking(status=BookingStatus.CONFIRMED, held_by=STAFF, held_at=at(6))
    second = booking(status=BookingStatus.CONFIRMED, held_by=STAFF, held_at=at(15))

    times = [booking_entries(b, COORDINATOR, at(20))[-1].occurred_at for b in (first, second)]

    assert times == [at(20), at(20)]


@pytest.mark.story("SCRUM-88")
@pytest.mark.parametrize(
    "status", [BookingStatus.TENTATIVE, BookingStatus.CANCELLED, BookingStatus.EXPIRED]
)
def test_only_a_confirmed_booking_has_a_confirmation_entry(status: BookingStatus) -> None:
    record = booking(status=status, held_by=STAFF, held_at=at(6), expires_at=at(8))

    assert HistoryAction.HOLD_CONFIRMED not in actions(booking_entries(record, COORDINATOR, at(9)))


@pytest.mark.story("SCRUM-88")
def test_an_unconfirmed_event_gives_a_confirmed_hold_no_confirmation_entry() -> None:
    record = booking(status=BookingStatus.CONFIRMED, held_by=STAFF, held_at=at(6))

    assert HistoryAction.HOLD_CONFIRMED not in actions(booking_entries(record, None, None))


@pytest.mark.story("SCRUM-88")
def test_an_expiry_is_the_systems_at_the_holds_expiry() -> None:
    record = booking(status=BookingStatus.EXPIRED, held_by=STAFF, held_at=at(6), expires_at=at(30))

    expired = booking_entries(record, None, None)[-1]

    assert expired.action is HistoryAction.HOLD_EXPIRED
    assert (expired.actor, expired.occurred_at) == (None, at(30))


@pytest.mark.story("SCRUM-88")
def test_an_expired_row_without_an_expiry_has_no_expiry_entry() -> None:
    """Defensive: the hold columns are written together, but the reader never invents a time."""
    record = booking(status=BookingStatus.EXPIRED)

    assert actions(booking_entries(record, None, None)) == [HistoryAction.VENUE_REQUESTED]


# ------------------------------------------------------------- visibility and ordering


@pytest.mark.story("SCRUM-88")
def test_note_entries_are_left_out_entirely_for_a_viewer_who_may_not_read_them() -> None:
    entries = [request_entries(request())[0], clarification_entry(note())]

    assert visible(entries, may_read_clarifications=True) == entries
    assert [e.source_type for e in visible(entries, may_read_clarifications=False)] == [
        HistorySource.EVENT_REQUEST
    ]


@pytest.mark.story("SCRUM-88")
def test_equal_times_fall_back_to_action_rank_then_record_id() -> None:
    low, high = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    base = HistoryEntry(
        HistoryAction.VENUE_REQUESTED, at(1), None, HistorySource.VENUE_BOOKING, high
    )
    same_action_lower_id = replace(base, source_id=low)
    earlier_rank = replace(base, action=HistoryAction.SUBMITTED)
    earlier_time = replace(base, action=HistoryAction.HOLD_EXPIRED, occurred_at=at(0))
    expected = [earlier_time, earlier_rank, same_action_lower_id, base]

    for shuffled in (expected[::-1], expected[1:] + expected[:1]):
        assert ordered(shuffled) == expected


@pytest.mark.story("SCRUM-88")
def test_the_timeline_has_every_readers_entries_once_and_oldest_first() -> None:
    """AC1, AC3, AC4: one record of each kind, with every action happening at the same
    instant, still gives each action once, in the fixed order."""
    record = request(
        submitted_at=at(0),
        decided_by=COORDINATOR,
        decided_at=at(0),
        confirmed_by=COORDINATOR,
        confirmed_at=at(0),
    )
    assignment = AssignmentRecord(uuid.uuid4(), None, COORDINATOR, LEAD, at(0))
    rejected = booking(
        status=BookingStatus.REJECTED, created_at=at(0), decided_by=STAFF, decided_at=at(0)
    )
    confirmed = booking(
        status=BookingStatus.CONFIRMED, created_at=at(0), held_by=STAFF, held_at=at(0)
    )

    entries = timeline(record, [assignment], [note(hours=0)], [rejected, confirmed], True)

    assert len({e.key for e in entries}) == len(entries) == 10
    assert actions(entries) == [
        HistoryAction.DRAFT_CREATED,
        HistoryAction.SUBMITTED,
        HistoryAction.REVIEW_DECIDED,
        HistoryAction.COORDINATOR_ASSIGNED,
        HistoryAction.CLARIFICATION_REQUESTED,
        *sorted([HistoryAction.VENUE_REQUESTED] * 2),
        HistoryAction.VENUE_DECIDED,
        HistoryAction.HOLD_CREATED,
        HistoryAction.HOLD_CONFIRMED,
    ]
    assert timeline(record, [assignment], [note(hours=0)], [rejected, confirmed], False) == [
        e for e in entries if e.source_type is not HistorySource.CLARIFICATION
    ]
