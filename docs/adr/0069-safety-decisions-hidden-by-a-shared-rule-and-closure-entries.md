# ADR-0069: Safety decision entries hidden by a shared rule, and venue closure entries

- **Status:** Proposed
- **Date:** 2026-10-28
- **Deciders:** Sheryl (approved the change to `core/dependencies.py` under AGENTS.md §6.3),
  whole team at review
- **Related stories:** SCRUM-120 (this PR: AC2 safety decisions, AC4 venue unavailability
  impact); SCRUM-79, SCRUM-81 and SCRUM-132 write the records
- **Extends:** ADR-0062 (history and its note filter), ADR-0067 (linked lifecycle entries)

## Context

SCRUM-120's last two sources:

- **Safety decisions (SCRUM-79):** one `safety_reviews` row per decision (approve, reject,
  request changes), never edited apart from the ADR-0052 invalidation marker, with the
  Officer, time and a required comment. Every decision is kept.
- **Venue closure impact (SCRUM-81):** one `venue_closure_impacts` row per save of a closure
  that hit a live arrangement: who saved it, when, the period and reason as they were then,
  and the affected booking ids across all events. Never changed afterwards. When a closure
  hits a Confirmed event, SCRUM-132 returns it to planning in the same transaction.

The comment is an internal operational judgement. `READ_SAFETY_REVIEWS` lets the Safety
Officer, any Lead and the current assignee read decisions, **not the owning Organiser**.
The history is read by the owner, the assignee and any Lead (ADR-0062), so without a
filter the owner would read every comment here. The rule existed only inline in the
`READ_SAFETY_REVIEWS` branch, and the history route cannot ask it without either a second
copy or an inline role check in the router (AGENTS.md §9).

## Decision

We will extract the rule as **`may_read_safety_reviews(request, roles, viewer_id)`** in
`core/dependencies.py`, called by the `READ_SAFETY_REVIEWS` branch and, through a new
`safety_review_visibility` dependency, by the history route. That is the same shape
ADR-0062 gave `may_read_clarifications`. The rule itself is unchanged, and the existing
safety-review access tests pass unchanged.

A viewer the rule refuses gets **no trace** of a decision: no entry, no comment, no id, as
ADR-0036 decided for internal notes. A test pins parity with
`GET /safety-reviews/{id}/history` for every viewer of the history, including an owner who
is also a Safety Officer and a Lead who is also the assignee. A return to planning is not a
decision; it stays visible to everyone, as ADR-0067 set out.

We will add two readers, appended after the earlier actions:

1. **Safety decision**: Officer, time, outcome (approved, rejected, changes requested) and
   comment.
2. **Venue closure**: Venue Staff member, time, venue, closure period, reason, and only this
   event's affected arrangements, as the buffer-change entry does (ADR-0064).

A return to planning caused by a closure now links that closure's entry, and takes its
actor from it. Closure causes are read from the closure entries the history already loads,
so the impact table is read once.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Show safety decisions to the owner | The comment is staff-side by SCRUM-79's own access decision; the history must not undo it |
| Show the owner the decision without its comment | Discloses that and when decisions were made, which ADR-0036 refuses for notes; it also needs the same viewer rule |
| Copy the rule into the history's domain | Two copies of an authorisation rule, kept equal only by a test, and the router would parse roles itself |
| Check `organiser_id == viewer` in the history service | An inline role check, rejected by AGENTS.md §9 |
| Show a closure that hit only another event's bookings | It has no link to this event; the buffer-change read made the same choice |

## Consequences

**Good**
- Safety visibility has one implementation, shared with the safety-review route.
- `READ_EVENT_HISTORY` and every other access rule are unchanged.

**Bad / accepted trade-offs**
- **New disclosure to the owner and Leads:** a closure's reason and the Venue Staff
  member's email, as ADR-0062 and ADR-0064 accepted for Venue Staff decisions and buffers.
- The owner still sees a return to planning, whose source is the invalidated approval's id
  (ADR-0067). The id carries no safety content.
- **Gap, AC4 (backlog):** deleting a closure is not recorded, and a closure that hit only
  pending requests has no impact row (SCRUM-81's rule), so neither is shown.
- Appended ranks: at one instant a return to planning lists before the closure that caused
  it, and links to it, as with change decisions (ADR-0068).

**What this makes harder to change later**
- Widening who reads safety decisions is an edit to `may_read_safety_reviews` and changes
  both routes together, which is the point.
