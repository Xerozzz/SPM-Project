# ADR-0018: Store the Venue Staff decision on the venue booking row

- **Status:** Proposed
- **Date:** 2026-10-03
- **Deciders:** Parikshit, reviewed by the team in PR
- **Related stories:** SCRUM-40 (review and reject), SCRUM-74 and SCRUM-75 (approve), SCRUM-54 (calendar)

## Context

Venue Staff must be able to reject a pending venue booking request with an optional reason,
and the Coordinator needs to see who decided, when and why so they can keep planning.
ADR-0015 already keeps every booking request as its own `venue_bookings` row, and a
rejected request is never overwritten: resubmitting creates a new row. Approval is built
in SCRUM-74 (ADR-0017), which left recording who approved and when to SCRUM-40. The
availability calendar (SCRUM-54) will read the same decision.

The customer also said one Venue Coordinator is responsible for a set of venues, but the
system has no link yet between staff and the venues they look after.

## Decision

We will add nullable `decided_by_id`, `decided_at` and `decision_reason` columns to
`venue_bookings`, filled once when a pending request is decided. Only a pending request can
be decided. Reject uses the same pending check style as approve in `domain/venue_booking.py`
and raises the same `InvalidBookingTransitionError`, so both decisions give the same 409.
The row is locked with SELECT ... FOR UPDATE before the check, as approve does, so two
decisions cannot both succeed. Any user with the Venue Staff role may decide any booking
for now.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A separate booking decision history table | Each request row is decided at most once and resubmission makes a new row (ADR-0015), so the row already is the history. A second table adds joins for no acceptance-criterion benefit. |
| Reuse the event request decision columns (ADR-0011) | That records the Coordinator's review of the event, a different decision by a different role. Mixing them would lose one of the two. |
| Check pending without locking the row | Two staff deciding at the same moment could both pass the check and the second would overwrite the first. |
| Restrict decisions to the staff member responsible for that venue | There is no staff to venue link in the data yet. Building one is outside SCRUM-40. |

## Consequences

**Good**
- Every decided request shows its decider, UTC time and reason, the same way event review decisions do (ADR-0011).
- Approve fills the same columns (SCRUM-75), passed into the SCRUM-74 approve service and stored in the same commit, so no second migration was needed.

**Bad / accepted trade-offs**
- Any Venue Staff member can decide a booking for any venue. Limiting this to the responsible Venue Coordinator needs a later story.

**What this makes harder to change later**
- Adding per-venue responsibility needs a new table or column and a change to the authorisation dependency, but no change to these decision columns.

## Notes

- Migration: `api/alembic/versions/0013_add_venue_booking_decision.py`.
