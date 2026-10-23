# ADR-0052: Mark a safety approval invalid when a Confirmed event goes back to planning

- **Status:** Proposed
- **Date:** 2026-10-23
- **Deciders:** Parikshit
- **Related stories:** SCRUM-130, SCRUM-47, SCRUM-79, SCRUM-80, SCRUM-132

## Context

An approved change request moves a Confirmed event back to Approved (ADR-0043). The
safety approval that let it be confirmed judged the old plan. ADR-0048 treats an approval
as stale when the plan fingerprint moves. Today that happens to cover this case, because
confirming turns the holds into confirmed bookings and the booking status is part of the
fingerprint. That is a side effect, not a rule. A change to a session or an equipment line
is only marked for replanning, so nothing in the plan itself records that the approval no
longer counts. SCRUM-130 asks for that to be explicit, and the approval history must stay.

## Decision

We will add `invalidated_at` and `invalidation_cause` to `safety_reviews`. One shared
service, `event_replanning.return_to_planning`, moves the event back to Approved and sets
these on the latest approval, inside the caller's transaction. Confirmation reads the
marker and reports `safety_approval_stale` until a new approval is recorded.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Rely on the fingerprint only | It only works because booking status is hashed. If the fingerprint ever stops covering status, an old approval would confirm a changed event. It also shows nothing in the history. |
| Delete the old approval | Loses who approved and when, which SCRUM-79 AC9 keeps. |
| Add an "invalidated" decision row | A decision row needs an Officer and a comment, and a new decision value would also reach the notification map. |

## Consequences

**Good**
- History is kept. The row just gains a reason it stopped counting.
- Change requests and venue closures reopen an event through one operation.

**Bad / accepted trade-offs**
- `safety_reviews` rows are no longer write-once. Only these two columns change, once.

**What this makes harder to change later**
- Any new way back to planning must call `return_to_planning` to stay consistent.
