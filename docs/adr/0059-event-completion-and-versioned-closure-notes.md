# ADR-0059: Complete an event in one transaction and keep closure notes as versions

- **Status:** Proposed
- **Date:** 2026-10-24
- **Deciders:** Parikshit
- **Related stories:** SCRUM-86, SCRUM-113, SCRUM-50, SCRUM-88, SCRUM-115

## Context

An event that has run needs a terminal status and a record of what happened: actual
attendance and operational notes. Corrections must not overwrite earlier values or who
recorded them. Completing must close open registration intake through SCRUM-113's own
operation, and must leave bookings, equipment reservations and registrations as they
were. SCRUM-50 later notifies on completion and SCRUM-88 later aggregates the history.

## Decision

We will add `completed` to the status machine as a terminal status reached only from
`confirmed`, at or after the event's end. `completed_by_id` and `completed_at` on the
event record the action SCRUM-50 will read. Closure notes live in `event_closure_notes`,
one row per version, never updated, with the newest as the current record. Completion
locks the event, closes open intake with SCRUM-113's staged `close`, moves the status,
and writes version 1, all in one commit.

Reading the closure record is for the owner, the current assigned Coordinator, any Lead,
and venue, technical or safety staff recorded as acting on the event (venue decisions and
holds, equipment changes and reservations, safety decisions).

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Columns on the event for attendance and notes | A correction would overwrite the earlier values (AC5). |
| A generic audit log table | More than this story needs. Versioned rows give history and the current value in one place, and SCRUM-88 can read them. |
| Call `close_intake` as it is | It commits on its own, so a later failure would leave intake closed on a Confirmed event. |
| Notify here | SCRUM-50 owns completion notifications. |

## Consequences

**Good**
- History is kept by construction, nothing is overwritten.
- Completion and the intake close land or roll back together.

**Bad / accepted trade-offs**
- Checking staff participation takes a few small queries per read.

**What this makes harder to change later**
- Any later terminal status (cancelled) has to be added to the same machine and the
  inactive set.
