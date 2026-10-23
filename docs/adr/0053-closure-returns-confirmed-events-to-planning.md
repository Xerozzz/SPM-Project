# ADR-0053: A venue closure returns the Confirmed events it affects to planning

- **Status:** Proposed
- **Date:** 2026-10-23
- **Deciders:** Parikshit
- **Related stories:** SCRUM-132, SCRUM-81, SCRUM-130, SCRUM-131

## Context

ADR-0044 records a closure over live bookings and notifies the Coordinators, but left
event status alone until safety review, confirmation and registration intake existed.
They exist now. A Confirmed event whose venue is shut should not keep looking confirmed.

## Decision

When a closure is saved, each Confirmed event with an affected arrangement goes through
`event_replanning.return_to_planning` (ADR-0052): back to Approved, safety approval
invalidated, new intake suspended. This happens in the same commit as the closure. Events
are locked in id order and checked again on the locked row, so a retry or a second
closure leaves an event already in planning alone. Moving, shortening or removing a
closure never reconfirms an event or restores an approval.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Only notify, as ADR-0044 did | The event keeps reading Confirmed while its venue is shut, and intake stays open. |
| Reconfirm when the closure is moved away | The approval and the arrangements need a person to check them again. |
| Replan in a later sweep | A crash between the closure and the sweep leaves a Confirmed event on a shut venue. |

## Consequences

**Good**
- Change requests and closures reopen an event the same way.
- A failed replan rolls back the closure, so there is no partial outcome.

**Bad / accepted trade-offs**
- Saving a closure now takes row locks on the affected events.

**What this makes harder to change later**
- Undoing a closure is a manual job for the Coordinator by design.
