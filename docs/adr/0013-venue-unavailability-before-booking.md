# ADR-0013: Record venue unavailability before booking allocation exists

- **Status:** Proposed
- **Date:** 2026-09-24
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-62, SCRUM-41, SCRUM-54

## Context

Venue Staff need to record maintenance and closure periods. The venue catalogue exists, but
the Availability Calendar and the booking/allocation workflow do not. In particular, there is
no booking table against which an unavailability period can be checked. ADR-0002 decides how
the future booking table prevents bookings from overlapping each other, but it does not provide
a cross-table constraint between bookings and closures.

## Decision

We will store each closure as a `venue_unavailabilities` row linked to an active venue, with
UTC start and end instants and a required reason. SCRUM-62 will expose CRUD API endpoints; a
future calendar reads these rows, and the future booking story owns the decision and database
design that prevents an allocation from overlapping them. Closure records entered in error are
removable operational data, rather than retained venue history, so SCRUM-62 uses hard deletion.
Deleting a closure never changes a booking.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Build booking allocation and conflict checks in SCRUM-62 | It expands this story into the unimplemented SCRUM-41 and risks a second, competing booking design. |
| Add an application-only booking overlap check now | There is no booking model, and an application check would conflict with ADR-0002's database-enforced invariant. |
| Add a calendar implementation now | SCRUM-54 owns calendar presentation and query behaviour; a CRUD list is sufficient integration data. |

## Consequences

**Good**
- Venue Staff can record, correct, and remove closures immediately.
- Future calendar and booking work has one persisted, authenticated source of closure data.

**Bad / accepted trade-offs**
- SCRUM-62 cannot reject a closure that overlaps a confirmed booking, or prevent a booking,
  until SCRUM-41 provides booking allocation and SCRUM-54 provides the calendar.
- The API represents overlapping closure records faithfully; it does not attempt general-purpose
  conflict detection that belongs to the booking story.
- A deleted closure cannot be recovered. We accept this because a closure recorded in error is
  operational noise, not historical venue data.

**What this makes harder to change later**
- The future booking design must deliberately incorporate this table or supersede this ADR with
  a shared allocation ledger; it cannot assume closures are merely presentation data.

## Notes

Historical booking rows are not changed by editing or deleting a closure. This is required by
SCRUM-62 AC6 and remains enforceable because this table has no write path to bookings.
