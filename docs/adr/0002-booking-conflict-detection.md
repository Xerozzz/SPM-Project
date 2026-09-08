# ADR-0002: Prevent booking conflicts with Postgres exclusion constraints

- **Status:** Accepted
- **Date:** 2026-09-08
- **Deciders:** Whole team
- **Related stories:** US-14 (booking conflict detection), US-17 (equipment reservation)

## Context

The customer requires that a confirmed venue booking makes that venue unavailable to other events
for the corresponding period, and that equipment already committed to an overlapping event is not
treated as freely available. This is the hardest correctness requirement in the release and the
one most likely to be probed in the Q&A.

The obvious implementation — query for overlapping bookings, then insert if none are found — is
a check-then-act race. Two coordinators approving bookings within the same moment both see a free
slot and both insert. Under the read-committed isolation Postgres uses by default, nothing stops
this. It is also difficult to demonstrate as *correct* rather than merely *usually working*.

## Decision

We will model booked periods as a `tstzrange` column and let PostgreSQL enforce non-overlap with
an exclusion constraint:

```sql
ALTER TABLE venue_booking ADD CONSTRAINT venue_booking_no_overlap
  EXCLUDE USING gist (
    venue_id WITH =,
    period   WITH &&
  ) WHERE (status = 'CONFIRMED');
```

The application keeps a pre-flight overlap check in `domain/scheduling.py` so users get a helpful
message before hitting the database, but correctness does not depend on it: the constraint
violation is caught in the service layer and translated into a 409 Conflict.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Application-level check-then-insert | Races under concurrency; correctness cannot be demonstrated, only hoped for |
| `SELECT ... FOR UPDATE` on the venue row | Works, but serialises all bookings for a venue and puts the invariant in code that is easy to forget to call |
| `SERIALIZABLE` isolation for the whole app | Correct but heavy-handed; adds retry logic everywhere for one invariant |
| A single-threaded booking queue | Over-engineered for the scale, and untestable within our timeframe |

## Consequences

**Good**
- The invariant cannot be violated, by any code path, including future ones we have not written.
- The concurrency case is testable: two parallel requests, one 201 and one 409.
- Ties us to a specific, defensible database capability — a strong Q&A answer about trade-offs.

**Bad / accepted trade-offs**
- Postgres-specific; the schema is no longer portable to SQLite or MySQL. We accept this and
  therefore run Postgres in tests via Docker rather than substituting SQLite.
- The `btree_gist` extension must be enabled in the first migration.
- Partial constraints mean cancelled and rejected bookings are excluded from the rule — the
  `WHERE` clause must be kept in step with the booking status vocabulary.

**What this makes harder to change later**
- Moving to another database engine would require re-implementing this invariant from scratch.
