# ADR-0054: Keep attendee registrations and their status history as separate records

- **Status:** Proposed
- **Date:** 2026-10-23
- **Related stories:** SCRUM-42, SCRUM-51, SCRUM-114

## Context

An attendee submission must survive intake closing, be ordered fairly for later organiser
decisions, reject concurrent duplicates, and retain a durable source action for later
notifications. The event-request table represents event planning and cannot represent an
attendee's repeated lifecycle history.

## Decision

We will store one registration row for each submission lifecycle, including the attendee's
submitted full name, age, phone number and optional dietary/accessibility notes, and an
append-only status history row for every transition. A locked event row assigns a
monotonically increasing per-event submission order. PostgreSQL enforces one live
(`pending`, `waitlisted`, or `accepted`) registration per attendee and event with a partial
unique index.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Store the current status on the event request | It cannot associate a status with an attendee or preserve history. |
| Check for duplicates only in the service | Concurrent requests could both pass the check before either writes. |
| Use venue capacity to choose an initial status | Capacity allocation is an organiser decision in SCRUM-114, not intake. |

## Consequences

**Good**
- Later acceptance, waiting-list and withdrawal stories share one ordered record and history.
- The initial history row is an immutable committed source action for SCRUM-51.

**Bad / accepted trade-offs**
- Each submission locks its event briefly so its ordering is deterministic.

**What this makes harder to change later**
- Changing which statuses are live requires an intentional index migration.
