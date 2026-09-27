# ADR-0014: Keep a search-only venue_bookings table until booking allocation lands

- **Status:** Proposed
- **Date:** 2026-09-26
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-55, SCRUM-41, SCRUM-62

## Context

Coordinator venue search (SCRUM-55) must exclude venues with a confirmed booking
overlapping the requested period, while pending requests never block. The booking and
allocation workflow (SCRUM-41) does not exist yet, so there is no booking table to read.
ADR-0013 records the same situation for closure periods: SCRUM-62 stores
`venue_unavailabilities` now, and the future booking story owns the design that prevents
an allocation from overlapping them. ADR-0002 decides how the future booking table
prevents bookings from overlapping each other, but it does not cover this search input.

## Decision

We will store each hold as a `venue_bookings` row linked to a venue, with UTC start and
end instants and a `BookingStatus` (`confirmed` blocks search, `pending` does not).
SCRUM-55 reads these rows only; SCRUM-41 owns the write path and the database design
that keeps them correct, and supersedes this ADR when it lands.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Build booking allocation inside SCRUM-55 | It expands this story into the unimplemented SCRUM-41 and risks a second, competing booking design. |
| Read the event-request table as the booking source | Event requests carry no venue or slot invariant, so search would exclude the wrong venues. |
| Skip the table and hard-code search fixtures | Search would have no persisted input to query, and SCRUM-41 would inherit no data shape. |

## Consequences

**Good**
- Search has one persisted, queryable source of hold data.
- SCRUM-41 inherits a concrete table shape and a closed status vocabulary to adopt or supersede.

**Bad / accepted trade-offs**
- Nothing prevents two `confirmed` rows from overlapping the same venue and slot until
  SCRUM-41 adds the write path and the ADR-0002-style invariant.
- SCRUM-55 cannot reject a hold that overlaps a closure block, or prevent a hold, until
  SCRUM-41 provides allocation.

**What this makes harder to change later**
- The future booking design must deliberately adopt this table or supersede this ADR with
  a shared allocation ledger; it cannot assume holds are merely search fixtures.
