# ADR-0056: Cancel one venue arrangement as a staged, row-locked transition

- **Status:** Proposed
- **Date:** 2026-10-22
- **Deciders:** Sheryl (approved the change to `require_event_access`, AGENTS.md §6.3), whole team at review
- **Related stories:** SCRUM-109; reused by SCRUM-115 and SCRUM-116
- **Extends:** ADR-0017 (booking-row lock), ADR-0019 (effective intervals), ADR-0026 (several arrangements per event), ADR-0030 (hold expiry)

## Context

An Approved event can have several venue arrangements at once (ADR-0026): pending
requests, tentative holds (ADR-0029, ADR-0030) and confirmed bookings. SCRUM-109 lets the
event's assigned Coordinator cancel one of them, with a reason, while the event is being
planned, leaving the others untouched. The cancelled record must keep its venue, period,
earlier decision and hold history, and must stop occupying the venue everywhere, buffers
included. A cancellation can race the hold-expiry timer, a Venue Staff decision or a hold
update on the same row, and exactly one outcome may win. SCRUM-115 (cancel a whole event)
and SCRUM-116 (replace a venue) will cancel arrangements inside their own transactions.

`BookingStatus.CANCELLED` already exists (SCRUM-73) but nothing sets it. The overlap
constraint already covers only `confirmed` and `tentative` rows over their effective
interval, and every application check reads the same `BLOCKING_STATUSES`.

## Decision

We will add a `cancel` transition, in the style of `approve`, `hold` and `expire`, to a
new pure module `domain/venue_cancellation.py` with the event and reason rules it is
always checked with: Pending, Confirmed and an *active* Tentative hold may be
cancelled; Cancelled, Rejected, Expired, and a hold whose expiry has been reached, may not.
The event rule allows **Approved only**, so a Confirmed event is refused with a pointer to
the controlled venue-change flow (SCRUM-118) and any other status, including ones added
later, is refused as not in planning.

Each booking gains `cancelled_by_id`, `cancelled_at` and `cancellation_reason` (migration
0038), required together when the status is `cancelled`. Decision and hold columns are
left as they were. Nothing is deleted. The exclusion constraint is not changed.

`services.venue_bookings.stage_cancellation` locks the **event row, then the booking row**,
applies the rules, writes the change and flushes **without committing**;
`cancel_arrangement` stages one and commits. Access is a new mode,
`EventAccess.CANCEL_VENUE_ARRANGEMENT`: the current assigned Coordinator, with no status
pin, so the service can say why a status is refused.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Delete the booking row | Loses the venue, period, decision and hold history the story requires |
| Record the cancellation in `decided_by_id` / `decision_reason` | Overwrites the Venue Staff decision that must be kept |
| Reuse the `SUBMIT_VENUE_BOOKING` access mode | It pins the event to Approved, so a Confirmed event would get a bare 403 instead of the venue-change message |
| List the event statuses that forbid cancelling | A status added later (Cancelled, Completed) would be allowed by default |
| Commit inside the operation | SCRUM-115 could not cancel several arrangements atomically |
| Widen or rewrite the exclusion constraint | It already ignores cancelled rows; changing it adds risk for no behaviour |

## Consequences

**Good**
- One more transition in the existing style; status is never assigned directly.
- A cancelled hold or booking frees its slot, buffers included, through rules that already
  exist: the constraint and `BLOCKING_STATUSES`.
- Races resolve under the row lock. The expiry timer skips a row being cancelled
  (`SKIP LOCKED`) and finds it no longer tentative; a cancel that waits on the timer reads
  the row as Expired and is refused. A hold at its exact expiry counts as expired, never
  as cancellable, so the two outcomes cannot both happen.

**Bad / accepted trade-offs**
- Locking the event row serialises a cancellation with other writes to the same event,
  such as submitting a new request. That is brief, and it is the order `submit` already
  uses, so no lock-order deadlock is introduced.
- A cancellation cannot be undone; the Coordinator makes a new request instead.

**What this makes harder to change later**
- Callers of `stage_cancellation` must own the commit and keep the event-then-booking lock
  order.
- When event statuses Cancelled or Completed arrive, they are refused automatically; allowing
  cancellation in any new status needs a deliberate change to the event rule.

## Notes

- The cancellation notification (SCRUM-49) and the Confirmed-event venue-change flow
  (SCRUM-118) are separate stories.
- Numbered 0056 because ADR-0049 to ADR-0055 merged first.
