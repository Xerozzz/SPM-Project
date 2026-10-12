# ADR-0021: Retain coordinator assignment history as an append-only audit trail

- **Status:** Proposed
- **Date:** 2026-10-12
- **Deciders:** Whole team
- **Related stories:** SCRUM-97 (Lead reassigns with history), SCRUM-98 (Lead assigns)
- **Extends:** ADR-0020 (manual coordinator assignment queue)

## Context

ADR-0020 made the Lead's assignment the first and only ownership write: `submit()`
leaves the request unassigned and `POST /event-requests/{id}/assign` records the
first owner on `event_requests.coordinator_id`. SCRUM-97 now needs ownership to
change hands — a Lead replaces the current Event Coordinator with another — without
losing accountability for who owned the request before, who moved it, and when.
Overwriting `coordinator_id` alone destroys that trail, and the acceptance criteria
require earlier entries to stay unchanged, chronological history reads, and
arrangements (details, clarifications, venue bookings) to survive reassignment.

## Decision

We will add an append-only `event_coordinator_assignments` table recording every
successful assignment and reassignment: event request, previous coordinator (null
for the first assignment), new coordinator, acting Lead, and a timezone-aware UTC
timestamp. Current ownership stays on `event_requests.coordinator_id` /
`assigned_at` for efficient authorisation (`require_event_access` reads one row);
history is the audit trail and never feeds the current-owner field. Application
flows never update or delete history rows. Reassignment locks the request row
(`SELECT ... FOR UPDATE`), compares the caller-supplied expected current owner
against the locked state, and commits the owner change plus the history row in one
transaction; a mismatch is `409 Conflict`, never last-write-wins.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Overwrite `coordinator_id` with no history table | Loses accountability; AC2 explicitly requires immutable previous/new/actor/time entries |
| Derive history from `decided_by_id` / audit logs | Decisions record who decided, not who owned; conflates two concerns and cannot show A→B→C chains |
| Keep history only in memory / in the UI | Not durable, not queryable, invisible to the next agent and to SCRUM-102 notifications |
| Backfill history for pre-migration assignments | The actor (which Lead) is unknowable after the fact; inventing one would falsify the audit trail. History starts with assignments made after this migration lands; earlier owners remain valid on the request row but have no history entries |

## Consequences

**Good**
- One ownership write path stays: initial assignment (SCRUM-98) and reassignment
  (SCRUM-97) both append history, so A→B→C chains are complete from here forward.
- Authorisation stays cheap: owner checks read the request row, history reads are
  separate and ordered by `assigned_at ASC, id ASC` for deterministic chronology.
- Concurrency is safe: row lock plus expected-owner comparison gives exactly one
  winner for concurrent reassignments from the same state.

**Bad / accepted trade-offs**
- Requests assigned before this migration have a current owner but zero history
  rows; the history endpoint returns an empty list for them rather than a
  reconstructed past. This is documented, not hidden.
- The reassign API requires the caller to send the expected current owner, so the
  UI must carry it from the overview it already displays. A stale UI gets a 409
  and refetches rather than silently overwriting.

**What this makes harder to change later**
- History rows are immutable by contract; correcting a mistaken entry needs a new
  compensating assignment, not an edit. SCRUM-102 will use the history row as the
  notification source, so its shape (previous/new/actor/time) is now depended on.
