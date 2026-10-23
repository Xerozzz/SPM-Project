# ADR-0044: Record venue closures over live commitments and report their impact

- **Status:** Proposed, event status rule superseded by ADR-0053
- **Date:** 2026-10-20
- **Deciders:** Parikshit
- **Related stories:** SCRUM-81, SCRUM-62, SCRUM-82, SCRUM-89, SCRUM-116, SCRUM-132

## Context

SCRUM-62 refused a venue closure that overlapped a confirmed booking (409), after end to
end testing found a venue that was both promised and shut. That kept the data tidy but
hid real problems: a burst pipe does not wait for a free slot, and Venue Staff had no way
to record it.

SCRUM-81 AC1 asks for the opposite: a valid closure is always recordable, even over
confirmed bookings and unexpired holds, and the affected arrangements are identified,
shown and their Coordinators notified, without cancelling anything.

SCRUM-89 already derives "this booking needs attention" on every read, and that check
already counts closures and live holds. So once a closure is allowed to overlap, the
existing staff and Coordinator displays show the problem with no new marker.

## Decision

- **The refusal is removed.** Create and update save any valid closure.
- **Impact is worked out on save** with the same buffered comparison approval uses
  (`domain.venue_closure_impact.affected_by_closure`), over the same live set SCRUM-89
  reviews: confirmed bookings and unexpired holds. Pending requests are not commitments
  and are not affected.
- **The save response lists the affected arrangements** so Venue Staff see at once what
  they hit.
- **One snapshot row per save that hit something** (`venue_closure_impacts`): who, when,
  the period, the reason and the affected booking ids. It has no foreign key to the
  closure, so it outlives a deleted closure for history (SCRUM-88) and replacement
  (SCRUM-116).
- **One inbox notification per affected arrangement** to the event's current assigned
  Coordinator, keyed on a deterministic uuid5 of (closure, period, booking). Re-saving
  the same period does not notify twice. Moving the closure notifies again for the new
  period. An event with no Coordinator is skipped without failing the save.
- **Closure, snapshot and notifications commit together.**
- **Nothing is cancelled or moved,** and the event status is not changed here. Returning
  affected Confirmed events to planning is SCRUM-132, once SCRUM-79, SCRUM-80 and
  SCRUM-113 exist.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep refusing closures over confirmed bookings | AC1 forbids it, and it leaves a real closure unrecorded. |
| Store an "affected" flag on each booking | SCRUM-89 already derives this on read. A stored flag would need clearing when the closure moves or is removed, and would go stale. |
| Key notifications on the snapshot row id | Each save makes a new row, so a retried save would notify twice. |

## Consequences

**Good**
- Venue Staff can always record a real closure, and the people who must act are told.
- The current state is never stored twice, so moving or removing a closure needs no
  cleanup.

**Bad / accepted trade-offs**
- A venue can now be both booked and closed until someone acts. The Coordinator display
  says "Needs attention" until it is resolved.
- Confirmed events affected by a closure stay Confirmed until SCRUM-132 lands.

**What this makes harder to change later**
- Going back to refusing closures would need these snapshot rows to be kept for history.
