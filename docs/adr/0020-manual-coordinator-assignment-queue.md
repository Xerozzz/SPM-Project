# ADR-0020: Assign event coordinators manually via a Coordinator Lead queue

- **Status:** Proposed
- **Date:** 2026-10-11
- **Deciders:** Whole team
- **Related stories:** SCRUM-101 (Lead views unassigned requests), SCRUM-98 (Lead assigns)
- **Supersedes:** ADR-0008 (round-robin coordinator assignment)

## Context

Week 7 changes how event requests get an owner. Under ADR-0008, `submit()` auto-assigned
an Event Coordinator by round-robin on first submission, skipping coordinators already
CONFIRMED that day. The module now wants a human decision instead: a Coordinator Lead
reviews newly submitted requests in an unassigned queue and picks each owner (SCRUM-98).
Submission must therefore leave the request unassigned, and the queue must show exactly
the Submitted requests with no coordinator, oldest first.

## Decision

We will stop assigning a coordinator at submission time and add a Lead-only unassigned
queue. `services/event_requests.submit()` moves a complete draft to SUBMITTED and stamps
`submitted_at`, leaving `coordinator_id` and `assigned_at` null. A new repository query
(`Submitted` plus `coordinator_id IS NULL`, ordered by `submitted_at ASC, id ASC`) backs
a Lead-only `GET /event-requests/unassigned` endpoint and UI queue. `COORDINATOR_LEAD`
joins the shared `Role` vocabulary; no separate boolean flag is introduced.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep round-robin and let the Lead reassign afterwards | Keeps two ownership paths and a misleading first owner; the story asks for unassigned-by-default so the Lead's choice is the first assignment |
| A boolean `is_lead` column on users | Duplicates the role vocabulary in a second mechanism; JWT claims, seed data and the frontend already speak roles, so a new role value is the smaller, consistent change |
| Queue as "all Submitted" with assignment shown as a column | Mixes the Lead's triage view with the coordinator review view; the acceptance criteria ask for unassigned-only with assigned rows excluded |

## Consequences

**Good**
- One ownership path: the Lead's assignment (SCRUM-98) is the first and only assignment,
  so there is no interim owner to explain or undo.
- Submission no longer fails when zero coordinators exist; the request simply waits in
  the queue.
- The queue ordering is deterministic: `submitted_at ASC` with `id ASC` as the stable
  secondary key for equal timestamps.

**Bad / accepted trade-offs**
- Submitted requests sit ownerless until a Lead acts; coordinator review/decision on an
  unassigned request must wait for (or be re-scoped by) assignment in SCRUM-98.
- The round-robin selector (`domain/coordinator_assignment.py`) and its pure unit tests
  stay in the tree unused for now; removing them is deferred so this PR stays within one
  story's scope.

**What this makes harder to change later**
- Reintroducing automatic assignment would need a new ADR superseding this one and a
  decision about what happens to requests already waiting in the queue.

## Notes

- ADR-0008 stays in the repository, marked superseded; its history explains the design
  being replaced.
- Seed data gains a `coordinator_lead@example.com` user; the approved sample can no
  longer rely on submit-time assignment and must assign through the SCRUM-98 path once
  it lands (interim: seed assigns the coordinator row directly, still via the status
  machine for the status itself).
