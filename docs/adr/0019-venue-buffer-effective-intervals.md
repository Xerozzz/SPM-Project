# ADR-0019: Store the effective occupied interval so the overlap constraint can see buffers

- **Status:** Proposed
- **Date:** 2026-10-07
- **Deciders:** Lee Yi Terng
- **Related stories:** SCRUM-82 (apply venue setup and turnaround buffers), SCRUM-89 (identify
  bookings affected by a buffer change)

## Context

SCRUM-82 requires that a venue's setup and turnaround time are included whenever availability and
conflicts are assessed. A booking's effective occupied interval runs from event start minus the
venue's setup time to event end plus its turnaround time, and AC4 names every rule that must use
it: venue search, the availability check, the availability calendar, conflict detection, and
booking approval **including the concurrent-approval safeguard**.

That last clause is the problem. ADR-0002 made the database the authority on overlap, and
ADR-0017 implemented it as a partial exclusion constraint on `venue_bookings`:

```sql
EXCLUDE USING gist (venue_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&)
WHERE (status = 'confirmed')
```

The buffers live on `venues`. **A Postgres exclusion constraint can only reference columns of its
own table**, so this constraint cannot be made buffer-aware as written. This is a capability limit,
not a preference: no amount of rewriting the expression reaches another table, and a generated
column cannot either.

There is a second, independent pressure. SCRUM-89 requires that changing a venue's buffers
*identifies* bookings that become problematic and explicitly never alters or refuses them (its AC3
and AC5). So the overlapping state has to be representable in the database. Any design where a
buffer change can be rejected by a constraint makes SCRUM-89 unimplementable.

## Decision

**Store the effective interval on the booking, move the constraint onto it, and treat the stored
pair as a snapshot taken when the booking is written rather than a value kept in step with the
venue.**

Migration 0015 adds `effective_start_at` and `effective_end_at` to `venue_bookings`, backfills
them from each venue's buffers, and replaces the constraint with one over
`tstzrange(effective_start_at, effective_end_at, '[)')`.

Two rules follow, and the second is the one that matters:

1. **The columns are written only by the code that writes the booking.** `submit` sets them;
   `approve` refreshes them from the venue's buffers as they are at that moment, because they may
   have changed since submission and the constraint reads them on commit.

2. **Nothing recomputes them when a venue's buffers change.** Every *application* check instead
   reads the venue's current buffers and widens as it compares, so search, the availability check,
   the calendar and conflict detection all reflect a buffer change immediately without touching a
   single booking row.

The widening itself lives in one pure module, `domain/venue_buffer.py`, with two deliberately
different comparisons: booking against booking widens both sides, because each booking needs its
own setup and reset; booking against a recorded closure widens only the booking, because a closure
already describes the whole period the venue is unusable.

SQL pre-filters use the identity that widening both sides of a comparison by the same amounts is
the same condition as requiring `setup + turnaround` of clear time between the raw intervals. That
keeps those queries reading raw columns, so they are unaffected by a stale snapshot. The identity
is proved by a test rather than asserted in a comment.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Denormalise `setup_minutes` / `turnaround_minutes` onto `venue_bookings` and compute the range in the constraint expression | Works, but stores two columns to derive two others, and has exactly the same staleness question with more to keep in step |
| Keep the constraint on event times and enforce buffers only in the application | Gives up ADR-0002's guarantee for precisely the overlaps buffers introduce: two bookings whose event periods do not overlap but whose effective intervals do could both be approved concurrently, and each per-booking row lock is held on a different row so they never serialise |
| Serialise approvals per venue with an advisory transaction lock instead | Would be correct, but ADR-0002 rejected per-venue locking for putting the invariant in code that is easy to forget to call, and that reasoning has not changed |
| Recompute the stored columns whenever buffers change | Makes a buffer change refusable by the constraint, which contradicts SCRUM-89 AC3 and AC5. Chosen against deliberately, see below |
| `SERIALIZABLE` isolation for the approval transaction | Already rejected by ADR-0002 as heavy-handed for one invariant; nothing here changes that |

## Consequences

**Good**
- ADR-0002's mechanism survives intact: the database still refuses two overlapping confirmed
  bookings, by any code path, now measured on effective intervals.
- A venue with zero buffers has an effective interval equal to its event period, so every
  behaviour that shipped before SCRUM-82 is unchanged without a single conditional (AC7).
- A buffer change never writes to `venue_bookings`, so it cannot fail, cannot be refused, and
  cannot lose data. SCRUM-89 is free to flag rather than refuse.
- The two asymmetric comparisons are named and separately tested, so nobody has to rediscover why
  a closure is not widened.

**Bad / accepted trade-offs**
- **The stored snapshot and the live rule can disagree.** After Venue Staff increase a buffer, two
  already-confirmed bookings may overlap under the new buffers while their stored intervals do
  not, and the constraint will not notice. This is the known gap, and it is what SCRUM-89 exists to
  surface. The application checks are always current, so nothing *new* can be approved into the
  overlap; only pre-existing confirmations can be caught out by it.
- SCRUM-89 has to surface that gap without needing the constraint changed. Its acceptance
  criteria were amended on 7 Oct 2026 to settle this: the "requires action" marker is derived
  from the venue's current buffers whenever it is read, not stored on the booking, so no
  migration and no change to this constraint's `WHERE` clause is needed. A stored flag would
  have required one, to keep a problematic booking representable, which is the version of this
  consequence an earlier draft of this ADR assumed.
- Two columns now hold derived data, which is a denormalisation. The check constraint
  `effective_start_at <= start_at AND effective_end_at >= end_at` is the backstop.
- Four queries now join `venues` to read buffers, where before they did not.

**What this makes harder to change later**
- Per-booking buffers, if the customer ever asks for them, would need the venue join removed from
  those queries and the snapshot rule revisited. AC1 currently forbids them, which is why the
  values live on the venue and no booking payload can express one.
- Any new booking status that should block availability has to be added to
  `booking_blocks_availability` *and* the constraint's `WHERE` clause, as ADR-0017 already warned.

## Open questions

- **Whether setup and turnaround must fall inside the venue's operating hours** is listed as a team
  decision on SCRUM-82 and is not implemented. Worth deciding with the wider picture in view:
  operating hours are currently enforced in exactly one place, `services/venue_search.py`. Booking
  submission and approval do not check them at all, so "buffers must fit inside opening hours"
  means extending a rule that merged stories do not apply yet.
- **Tentative holds**, named in SCRUM-82 AC5, do not exist in this codebase. `BookingStatus` is
  confirmed, pending, rejected and cancelled. The half of AC5 that does exist, a booking's
  effective interval against recorded venue unavailability, is implemented.
