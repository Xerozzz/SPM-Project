# ADR-0066: Cancelling an arrangement of a Confirmed event is a venue change that returns it to planning

- **Status:** Proposed
- **Date:** 2026-10-27
- **Deciders:** Sheryl, whole team at review
- **Related stories:** SCRUM-118; SCRUM-109, SCRUM-130, SCRUM-131, SCRUM-132, SCRUM-50
- **Extends:** ADR-0056 (cancel one arrangement), ADR-0052 and ADR-0053 (return to planning)

## Context

SCRUM-109 lets the assigned Coordinator cancel one arrangement while the event is being
planned, and refuses a Confirmed event with "change its venue through the venue-change
process" (ADR-0056). SCRUM-118 is that process. A Confirmed event cannot simply lose an
arrangement: what was confirmed, and what the safety approval judged, no longer exists.
So the Coordinator has to confirm that cancelling starts a venue change, and in the same
action the event must go back to planning, with its safety approval no longer counting and
new registrations suspended. If any part fails, nothing may change.

Both halves already exist. SCRUM-109's `stage_cancellation` cancels one arrangement in
the caller's transaction, locking the event and then the booking. `return_to_planning`
(ADR-0052) moves a Confirmed event back to Approved through the status machine,
invalidates its current safety approval, suspends intake, and stages the SCRUM-50 "event
replanned" notices. Change requests (SCRUM-47) and venue closures (SCRUM-132) both use it.

Nothing on main lists a Confirmed event's arrangements to its Coordinator: the planning
list (`GET .../venue-bookings`) is pinned to Approved.

## Decision

We will add `POST /event-requests/{id}/venue-bookings/{booking_id}/venue-change` with
`{reason, confirm_venue_change}`, for the current assigned Coordinator
(`CANCEL_VENUE_ARRANGEMENT`, no status pin). Without `confirm_venue_change: true`, or
without a reason, it answers 422 before reading anything. Otherwise
`services.venue_changes` calls `stage_cancellation` with `venue_change=True`, which allows
only a Confirmed event, then `return_to_planning` with a new cause, `venue_cancellation`,
and commits once. Any exception rolls both back.

SCRUM-109's cancel endpoint is unchanged except its 409 message for a Confirmed event,
which now names the venue change. We will also add `GET /event-requests/{id}/venue-arrangements`
under the same access mode, listing the event's arrangements in any status, so the
Coordinator can see and cancel a Confirmed event's arrangements.

**The "event replanned" notices are deliberate, not scope creep.** They are staged by the
shared `return_to_planning`, exactly as for a venue closure, and the Week 9 clarification
says venue problems with a Confirmed event should notify its stakeholders. Delivering them
stays SCRUM-50's; this story only stages them in the same transaction.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A `confirm_venue_change` flag on the existing cancel endpoint | One route would then sometimes change the event's status; SCRUM-109's cancel is defined as never touching it |
| Reimplement the replanning steps in the cancellation service | A second copy of status, safety and intake rules that could drift from the one change requests and closures use |
| Cancel and replan in two separate commits | A failure between them would leave a Confirmed event missing an arrangement, which AC3 forbids |
| Confirm only in the UI | The API could be called without it; the confirmation is enforced as a required field |
| Widen `SUBMIT_VENUE_BOOKING` to list a Confirmed event's bookings | It is also what allows new requests; a read route on the cancel permission widens nothing |
| Stage no notifications for this cause | Would mean not reusing `return_to_planning`, and stakeholders would not hear of the change |

## Consequences

**Good**
- One transaction, two shared operations, the SCRUM-109 lock order and refusals unchanged.
- Reconfirmation needs the normal path again: a new safety approval, then manual
  confirmation (SCRUM-79/80). Nothing here reconfirms.
- No migration: `safety_reviews.invalidation_cause` is a free `String(32)`.

**Bad / accepted trade-offs**
- Attendees and affected staff get an "event replanned" notice for an arrangement cancellation.
- Intake stays suspended after reconfirmation until the Organiser reopens it (SCRUM-131).

**What this makes harder to change later**
- `stage_cancellation(..., venue_change=True)` is now a second entry into SCRUM-109's rule;
  a third mode should be its own function, not another flag.
