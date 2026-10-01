# ADR-0016: Ship the application booking-conflict check before the exclusion constraint

- **Status:** Proposed
- **Date:** 2026-10-01
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-73, SCRUM-74, SCRUM-40, SCRUM-62
- **Relates to:** ADR-0002, ADR-0013, ADR-0015

## Context

ADR-0002 makes the database the authority on booking overlap (a `tstzrange` exclusion
constraint over confirmed rows), with an application pre-flight check only for friendly
errors. The work has been split: SCRUM-73 delivers conflict *detection* — refusing approval
and naming the blocking booking or closure — and SCRUM-74 delivers *concurrency*: the
constraint, its migration, and approval authorisation. No approve action exists yet; SCRUM-40
owns it. ADR-0013 left closures (`venue_unavailabilities`) for the booking story to enforce,
and an exclusion constraint cannot span two tables, so closures need an application check
regardless.

## Decision

We will ship the application check first, as `domain.booking_conflict.ensure_no_conflict`,
called from `services.venue_bookings.check_approvable`. It reuses
`domain.venue_search.intervals_overlap` and `booking_blocks_availability`, so search and
approval share one half-open overlap rule and one definition of "blocking status". It takes
no locks and adds no route; SCRUM-40's approve action calls it before changing status.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Land the exclusion constraint in SCRUM-73 | Doubles the story and mixes in concurrency testing that SCRUM-74 exists to own; the PR would exceed our ~400-line limit. |
| `SELECT ... FOR UPDATE` on the venue in the check | Rejected by ADR-0002 as the long-term mechanism; adding it now would be thrown away by SCRUM-74. |
| A second `intervals_overlap` in `booking_conflict.py` | Two copies of the most-questioned rule could drift; search and approval must agree on adjacency. |

## Consequences

**Good**
- Every SCRUM-73 acceptance criterion is provable by fast domain tests plus service tests on Postgres.
- SCRUM-74's constraint can be added without changing this check's behaviour or messages.

**Bad / accepted trade-offs**
- Until SCRUM-74 merges, two simultaneous approvals for overlapping periods can both pass —
  the check-then-act race ADR-0002 describes. No approve route exists today, so the race is not
  yet reachable; if SCRUM-40 ships one before SCRUM-74, that PR must accept this window explicitly.
- Closures stay application-checked even after SCRUM-74; a closure recorded *after* a booking
  is confirmed is not detected (ADR-0013 already accepts this).
- `BookingStatus.CANCELLED` is added with no code path setting it yet.

**What this makes harder to change later**
- SCRUM-74's constraint `WHERE` clause must match `booking_blocks_availability` exactly
  (only `confirmed` blocks), or the friendly check and the constraint will disagree.

## Notes

ADR-0002 names `domain/scheduling.py` for the pre-flight check; it lives in
`domain/booking_conflict.py` instead, beside the other venue domain modules.
