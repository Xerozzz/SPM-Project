# ADR-0026: Allow independent venue booking requests for one event

- **Status:** Proposed
- **Date:** 2026-10-13
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-78, SCRUM-38, SCRUM-71
- **Supersedes:** ADR-0015's per-event pending-request restriction only

## Context

SCRUM-78 and the Week 9 customer clarification allow parallel tracks and multiple
spaces within one event. ADR-0015's event-wide pending check prevents requesting
Venue B while Venue A is pending, although storage already supports several booking
rows per event. The customer also distinguishes tentative holds, which occupy a
venue's slot until expiry, from the request lifecycle implemented on main.

## Decision

We will use the existing one-to-many EventRequest → VenueBooking association and
insert a fresh row for each successful request. Each booking retains its own ID,
venue, period, status and decision metadata; deciding one leaves siblings unchanged.
Pending existence will no longer prohibit another request for the event, and the
frontend will show booking history alongside the request form. The existing event
row lock remains, but no pending-history check follows it.

Suitability remains advisory and is evaluated independently against each selected
venue, without combining capacities or other attributes. Authorization remains in
the shared assigned-Coordinator dependency; approval and rejection remain Venue
Staff decisions by booking ID.

Availability and conflict rules remain venue-specific, including each venue's buffers.
Current PENDING rows are requests, not tentative holds: they do not block search,
availability or approval. Confirmed overlaps and recorded closures block approval;
the exclusion constraint protects confirmed overlaps under concurrency (ADR-0017/0019).
Submission still does not independently enforce availability. We will preserve these
rules rather than map PENDING to a new hold meaning. Tentative holds and their expiry
are not implemented on main and remain a separate customer-change dependency.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep one pending request per event | Prevents requesting parallel venues required by SCRUM-78. |
| Replace the existing booking when another venue is selected | Loses independent arrangements and audit history. |
| Add an event/venue uniqueness rule or reinterpret PENDING as a hold | Introduces policy and conflict semantics beyond the implemented request lifecycle. |

## Consequences

**Good**
- Additional venues can be requested while siblings are pending; rejected history remains.
- The existing non-unique event foreign key supports this without a migration.

**Bad / accepted trade-offs**
- Same-venue/time pending requests can coexist; only one overlapping request can be confirmed.
- The customer's tentative-hold occupancy requirement remains dependent on the separate hold story.

**What this makes harder to change later**
- Introducing holds must define their occupancy and expiry explicitly, rather than silently
  treating all PENDING requests as holds.

## Notes

ADR-0015's table choice, audit links and advisory suitability remain applicable.
SCRUM-78 adds no cancellation/edit workflow, combined-capacity planning or new status.
