# ADR-0015: Adopt venue_bookings for pending venue requests

- **Status:** Superseded by ADR-0026 (per-event pending-request restriction)
- **Date:** 2026-09-28
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-38, SCRUM-40, SCRUM-41
- **Supersedes:** ADR-0014's search-only limitation

## Context

ADR-0014 made `venue_bookings` search-only. SCRUM-38 needs auditable pending requests
linked to an approved event and submitting Coordinator. SCRUM-40 then needs a stable
row to approve or reject, and SCRUM-41 later needs the same table to become the confirmed
booking ledger with database-backed conflict protection.

The venue search path already excludes venues with overlapping closure/unavailability
blocks and confirmed bookings. SCRUM-38 is narrower: it records a Coordinator's request
for an approved event after the Coordinator has selected a venue.

## Decision

SCRUM-38 adopts `venue_bookings` for pending venue requests. New rows link to
`event_requests` and `users`, and those links are required because main has no persisted
legacy booking rows outside tests. Locking the event before checking for a pending row
serialises submissions. Rejection retains the row and resubmission inserts another.

Venue search excludes unavailable venues, but SCRUM-38 submission does not independently
enforce venue availability or booking conflicts. That is deliberate: SCRUM-41 still owns
confirmation and the database invariant that prevents overlapping confirmed bookings.
SCRUM-40 still owns approval/rejection decisions.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Create a separate `venue_booking_requests` table | It would force SCRUM-40/SCRUM-41 to reconcile request rows with booking rows later, even though both represent the same venue/time request lifecycle. |
| Keep `venue_bookings` search-only until SCRUM-41 | SCRUM-38 would have nowhere durable to store a Coordinator's pending request, and SCRUM-40 could not address a specific request. |
| Enforce venue availability and conflicts during SCRUM-38 submission | It would move SCRUM-41's confirmation invariant into a pending-request story and risk two competing conflict designs. |
| Keep event/requester links nullable for old test fixtures | Main has no legacy rows that need the weakness, and nullable links would make real pending requests harder to audit. |

## Consequences

**Good**
- Pending venue requests become auditable rows with stable ids for SCRUM-40 decisions.
- Search still treats only `confirmed` rows as blocking, so pending demand does not hide venues.
- Non-null event and requester links make every booking request explainable from its event and Coordinator.

**Bad / accepted trade-offs**
- Suitability remains advisory and event status is unchanged after submission.
- A venue that becomes unavailable after search can still receive a pending SCRUM-38 request.
- Duplicate pending requests are rejected per event, but rejected history is retained and does not block resubmission.

**What this makes harder to change later**
- SCRUM-40 and SCRUM-41 must continue the lifecycle on `venue_bookings` or deliberately supersede this ADR.
- SCRUM-41 must add conflict and availability enforcement without relying on SCRUM-38 having pre-filtered every submission.
- If the product later adds venue-type metadata, suitability can start comparing `venue_requirement`, but that will require a venue schema change rather than a hidden string match in SCRUM-38.
