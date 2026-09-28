# ADR-0015: Adopt venue_bookings for pending venue requests

- **Status:** Proposed
- **Date:** 2026-09-28
- **Related stories:** SCRUM-38, SCRUM-40, SCRUM-41
- **Supersedes:** ADR-0014's search-only limitation

## Context

ADR-0014 made `venue_bookings` search-only. SCRUM-38 needs auditable pending requests
linked to an approved event and submitting Coordinator.

## Decision

SCRUM-38 adopts that table. New requests link to `event_requests` and `users`; nullable
columns preserve old scaffold rows. Locking the event before checking for a pending row
serialises submissions. Rejection retains the row and resubmission inserts another.

SCRUM-40 still owns decisions; SCRUM-41 owns confirmation and conflict constraints.

## Consequences

- Search still treats only `confirmed` rows as blocking.
- Suitability remains advisory and event status is unchanged.
