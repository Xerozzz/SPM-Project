# ADR-0008: Derive round-robin coordinator assignment from assignment history

- **Status:** Superseded by ADR-0020
- **Date:** 2026-09-13
- **Deciders:** Whole team
- **Related stories:** SCRUM-34 (auto-assign an Event Coordinator on first submission)

## Context

CONFIRMED is pre-declared in EventStatus for this rule but not yet reachable by
any transition in this release — no story here moves an event into CONFIRMED.
The round-robin skip rule is written against CONFIRMED now so it doesn't need
revisiting when a future story (auto-confirmation once arrangements settle)
lands.

This lands after SCRUM-46 already merged `event_requests`, its `EventStatus` machine
(ADR-0006), and the organiser-facing submit/list/edit endpoints. SCRUM-34 hooks into the
existing `submit()` service function rather than inventing a parallel event model.

## Decision

We will derive "whose turn is next" from the `event_requests` table itself — the coordinator
on the most recently assigned request, ordered by `assigned_at` — rather than keeping a
separate rotation-pointer table. `domain/coordinator_assignment.py` takes that value plus the
ordered pool of active coordinators (`repositories/users.py`, ordered by account creation)
and the set of coordinators already busy that date, and returns the next assignee as a pure
function. `services/event_requests.submit()` calls it once, only when the request does not
already have a `coordinator_id` — which in practice means only on the request's first ever
successful submission, since the status machine (ADR-0006) refuses a second `submit()`
outright.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A dedicated `coordinator_rotation` table with a single "last assigned" pointer | An extra table and migration for state that is already implied by `event_requests`; another place the two could drift out of sync |
| Assign uniformly at random | Simpler, but not what the story asks for and harder to explain or reproduce in a demo |
| A round-robin index stored in application memory | Lost on every restart and wrong the moment there is more than one API process |
| A new `Event` model parallel to `event_requests` | The first draft of this story built exactly this before SCRUM-46 merged; keeping it would leave two competing event models in the codebase for one workflow |

## Consequences

**Good**
- One less table; the rotation position is always consistent with the requests that
  actually exist, including after a restart.
- The selection rule itself (`select_next_coordinator`) is a pure function with no I/O,
  so it is covered exhaustively by fast unit tests per AGENTS.md §4.
- Builds on the already-merged submission flow instead of duplicating it.

**Bad / accepted trade-offs**
- Two organisers submitting at the same instant can both read the same "last assigned"
  coordinator and both be pointed at the same next one, so the rotation can skip or repeat
  a coordinator under concurrency. We accept this: fairness of rotation is a soft goal, not
  a correctness invariant like the double-booking case in ADR-0002 — nobody ends up double
  booked, at worst one coordinator gets two requests in a row before the next one catches up.
- If the coordinator last assigned has since become inactive, the rotation restarts from the
  front of the current active pool rather than resuming exactly where it left off.

**What this makes harder to change later**
- If true fairness under concurrency is ever required, this needs a real serialisation point
  (e.g. `SELECT ... FOR UPDATE` on a rotation row, the same technique `get_for_update` already
  uses for the submit-twice race) — a superseding ADR, not a patch.

## Notes

- Reassignment (moving an already-assigned request to a different coordinator) and
  accept/decline are explicitly out of scope for SCRUM-34 and are not implemented here.
- The ticket's "Confirmed event" is this codebase's `EventStatus.CONFIRMED`, added to
  `domain/event_status.py` as a vocabulary member only — no transition into it exists yet.
  That transition is SCRUM-31's ("review and decide"), per ADR-0006's invitation for each
  story to extend the shared status file. Until SCRUM-31 ships, the conflict rule is exercised
  by tests that set `status=APPROVED` directly (the same test-arrange pattern SCRUM-46's own
  tests use for DRAFT/SUBMITTED rows) rather than by any reachable production code path.
