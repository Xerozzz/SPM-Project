# ADR-0055: Record the actor on registration status history

- **Status:** Proposed
- **Date:** 2026-10-23
- **Related stories:** SCRUM-128, SCRUM-42, SCRUM-51, SCRUM-114

## Context

ADR-0054 established immutable registration status history as the source action for later
registration and notification work. Its original columns capture the transition and time,
but do not identify who performed a later transition such as an attendee withdrawal.

## Decision

Each `event_registration_history` record will store a non-null `actor_id`. Existing initial
submission history is backfilled from its registration attendee; future transitions record
the authenticated actor in the same transaction as the current-status update.

## Alternatives considered

| Option | Why we rejected it |
| --- | --- |
| Add a separate withdrawal audit table | Duplicates ADR-0054's append-only source-action mechanism. |
| Infer every actor from the registration attendee | It cannot accurately represent future organiser decisions. |

## Consequences

**Good**
- Withdrawal and later decisions have a single durable, attributable source action.

**Bad / accepted trade-offs**
- The new foreign key adds one required value to every history write.

**What this makes harder to change later**
- A system actor would need a deliberate representation rather than a null actor.
