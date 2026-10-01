# ADR-0017: Enforce booking approval with the exclusion constraint and a booking-row lock

- **Status:** Proposed
- **Date:** 2026-10-02
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-74, SCRUM-40 (approve action absorbed here), SCRUM-73
- **Relates to:** ADR-0002, ADR-0016

## Context

ADR-0016 shipped the application conflict check (SCRUM-73) and left the race it cannot
close to SCRUM-74: two venue staff approving overlapping requests at the same instant both
pass the check. SCRUM-74's acceptance criteria also need an approve action to authorise,
and ADR-0016 assigned that action to SCRUM-40, which has not been started. Without a route,
neither "exactly one of two simultaneous approvals succeeds" nor "an unauthorised user is
refused with 403" can be demonstrated.

## Decision

We will:

1. Add ADR-0002's constraint to `venue_bookings` (migration 0012) as
   `EXCLUDE USING gist (venue_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&)
   WHERE (status = 'confirmed')`. The range is an expression over the existing columns,
   half-open like `intervals_overlap`, and the `WHERE` matches `booking_blocks_availability`.
2. Build the approve action here: `POST /api/venue-bookings/{id}/approve`, guarded by
   `require_role(Role.VENUE_STAFF)`. **This absorbs SCRUM-40's approve action**; SCRUM-40
   should reuse it rather than add a second one.
3. In `services.venue_bookings.approve`, take `SELECT ... FOR UPDATE` on **the booking row
   only**, check the pending → confirmed transition, run the SCRUM-73 check, and commit. The
   repository turns only an exclusion violation (SQLSTATE 23P01) into
   `ConcurrentBookingConflictError`, which the router reports as 409.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Lock the venue row | Rejected in ADR-0002: serialises every approval for a venue and leaves the invariant in code that can be forgotten. |
| Constraint only, no row lock | Two approvals of the *same* request would both run and could both report success; the lock makes the second see `confirmed` and be refused. |
| Leave the route to SCRUM-40 | SCRUM-74's ACs could only be proven at the service layer, and the authorisation AC not at all. |
| A new stored `period tstzrange` column | Duplicates start_at/end_at and needs a backfill and a sync rule; the expression index gives the same guarantee. |

## Consequences

**Good**
- Overlapping confirmed bookings cannot exist, whichever code path confirms them.
- Both ACs are tested through HTTP and real PostgreSQL, including a two-thread race.

**Bad / accepted trade-offs**
- SCRUM-40's approve action is done in this story; its ticket must be re-scoped (reject, UI).
- When the friendly check races, the refusal is generic ("confirmed at the same time")
  rather than naming the other booking.
- Who approved and when is not recorded; that needs a schema change and is left to SCRUM-40.
- Closures are still application-checked only (ADR-0013, ADR-0016).

**What this makes harder to change later**
- Any new blocking booking status must be added to both `booking_blocks_availability` and
  the constraint's `WHERE` clause, via a new migration.
