# ADR-0040: Store the session label on the venue booking row

- **Status:** Proposed
- **Date:** 2026-10-20
- **Deciders:** Alvin
- **Related stories:** SCRUM-111

## Context

A venue request is one session of its parent event: a label plus the period that
session needs the venue for. The `venue_bookings` row already carries a per-row
`start_at/end_at`, but nothing names which session the row is for, so parallel
sessions at different venues cannot be told apart by the Coordinator or Venue Staff.

## Decision

We will add a non-blank `session_label` text column to `venue_bookings` (migration
0025) and treat the row's existing `start_at/end_at` as the session's requested
period. Pre-existing whole-event rows are backfilled from their parent event's name.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A separate `event_sessions` table with a foreign key from the booking | No session exists outside a venue request yet; a table for one label would add a join to every booking read for no current use. |
| Per-session attendance or suitability columns beside the label | SCRUM-111 AC4 reuses suitability against the event's recorded requirements; per-session scoring is a second engine nobody asked for. |

## Consequences

**Good**
- One row stays one self-contained request: label, period, venue and decision travel together through search, conflict, calendar and staff views.
- Existing rows keep their recorded periods; the backfill gives them an honest label without inventing sessions.

**Bad / accepted trade-offs**
- Two sessions sharing a label are distinguishable only by period and venue; uniqueness is a display concern, not a constraint.
- If sessions later gain their own lifecycle, this column becomes the seed of that table rather than its final shape.

**What this makes harder to change later**
- Renaming the label later means migrating every booking row rather than one session row.

## Notes

Handoff: `AGENTS-sprint4-Alvin.md` (SCRUM-111). Schema rule: AGENTS.md §3.
