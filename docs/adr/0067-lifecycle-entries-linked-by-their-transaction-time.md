# ADR-0067: Lifecycle entries in the event history, linked by their shared transaction time

- **Status:** Proposed
- **Date:** 2026-10-28
- **Deciders:** Sheryl, whole team at review
- **Related stories:** SCRUM-120 (this PR: AC3 confirmation and return to planning, AC6
  cancellation); later SCRUM-120 PRs add change requests, completion, safety and closures
- **Extends:** ADR-0062 (history from retained records), ADR-0064 (venue entries)

## Context

SCRUM-120 adds the event's lifecycle decisions to the history ADR-0062 builds from existing
records. This PR covers confirmation, every return to planning, and the cancellation of the
whole event. What the records keep:

- **Confirmation (SCRUM-80):** `event_requests.confirmed_by_id` / `confirmed_at`, holding
  only the latest. Confirming a replanned event again overwrites them, and nothing else
  records the earlier confirmation (the ADR-0062 gap). A return to planning does not clear
  them.
- **Return to planning (SCRUM-130):** no row of its own. `return_to_planning` sets the
  status, suspends intake, stages notices, and marks the event's current safety approval
  `invalidated_at` / `invalidation_cause`. Confirming needs an approval that counts and
  safety decisions are refused outside planning, so every return marks exactly one
  approval. The marker has a time and a cause but no actor.
- **What caused it:** an approved change request (`decided_by_id`, `decided_at`), a closure
  (`venue_closure_impacts.recorded_by_id`, `recorded_at`), or a venue change (the booking's
  `cancelled_by_id`, `cancelled_at`). Each is written in the same transaction as the return,
  stamped with the same `now`.
- **Cancellation (SCRUM-115):** `event_requests.cancelled_by_id` / `cancelled_at` /
  `cancellation_reason`, once. In the same transaction it cancels each live arrangement and
  releases each reservation with the same actor and `now`. Those already have SCRUM-119
  entries.

## Decision

We will add three readers and three actions, appended after SCRUM-119's:

1. **Event confirmed**, from the event's confirmation columns: the latest confirmation only.
2. **Returned to planning**, one per invalidated approval, with its time and cause. Its actor
   is the actor of the cause action with the **same cause and exactly the same time**. If
   there is not exactly one such action, the entry has no actor and `actor_recorded` is
   false; the UI shows "actor not recorded", never "System" and never a guess.
3. **Event cancelled**, once, with its actor and reason.

Event-level entries **link** to the entries they are about instead of repeating them, through
a new `related_entry_ids` list of entry `id`s (`action:source_id`). The cancellation links the
`arrangement_cancelled` and `reservation_released` entries with its own actor and exact time.
A return to planning caused by a venue change links that arrangement's cancellation. A change
request decision or closure has no entry yet, so that return names its actor and links
nothing until the later PRs add those entries.

The matching is exact equality on values one transaction wrote, not nearness. Unit and
integration tests pin both the match and the no-match case, including a cause one
microsecond away.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Record each return to planning, with its actor, in a new table | A migration and a writer change in a read-only story; earlier returns would still have no row |
| Show the return with a null actor, as the system | False: a person decided the change, saved the closure or cancelled the arrangement |
| Take the nearest cause in time | A guess; two actions a second apart would be indistinguishable from one cause |
| Copy the released arrangements into the cancellation entry | Shows each release twice and the two copies could disagree; AC6 asks for a link |
| Hide the per-arrangement cancellations under the event entry | They are complete records of each booking's own change (ADR-0064 kept them for that reason) |
| Insert the new actions before related SCRUM-119 ones | Would read slightly better at one instant, but changes ranks other tests and readers rely on |

## Consequences

**Good**
- No migration, no writer, route, access rule or ordering change; the timeline gains two
  optional sources, as SCRUM-119's did.
- The owner, assignee and Lead see the same new entries; none carries private text that the
  cancellation and confirmation screens do not already show them.

**Bad / accepted trade-offs**
- **Gap, AC3 (backlog):** only the latest confirmation is shown. After replan and
  reconfirmation the first confirmation is gone. Keeping each needs a confirmations record.
- **Gap, AC3 (backlog):** a return to planning has no record of its own. Its actor depends on
  the cause action sharing the transaction's `now`; a writer that stops doing so turns the
  entry into "actor not recorded" (safely, but silently). The integration tests would catch it.
- Appended ranks mean that at one instant "Hold confirmed" lists before "Event confirmed",
  and released arrangements before "Event cancelled", which then reads as a summary.
- The return entry's source is the safety approval it invalidated (`safety_review`), shown
  as an id only; no safety content is read for it.

**What this makes harder to change later**
- `related_entry_ids` refers to entry ids, so `action:source_id` is now a contract between
  entries, not only a React key.
- A writer that sends an event back to planning must keep stamping its cause with the same
  `now`, or the actor is lost.

## Notes

- Hiding safety decision entries from the owner (a shared `may_read_safety_reviews` rule in
  `core/dependencies.py`, approved by Sheryl under AGENTS.md §6.3) is recorded in the ADR of
  the PR that adds those entries. The return-to-planning entry is not a safety decision and
  is shown to the whole history audience.
