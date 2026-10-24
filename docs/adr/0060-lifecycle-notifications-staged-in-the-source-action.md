# ADR-0060: Stage lifecycle notifications in the source action, keyed once per action

- **Status:** Proposed
- **Date:** 2026-10-24
- **Deciders:** Parikshit
- **Related stories:** SCRUM-50, SCRUM-99, SCRUM-37, SCRUM-47, SCRUM-79, SCRUM-80, SCRUM-81, SCRUM-86, SCRUM-130, SCRUM-132

## Context

Several finished workflows need to tell people what happened: a change proposed or
decided, a plan ready for safety review, a safety decision, a confirmation, a return to
planning and a completion. SCRUM-99 already stores notifications with a unique
(recipient, source type, source id), and ADR-0022 says producers stage them in their own
transaction. A plan becoming reviewable has no single action of its own, and the story
asks that an unchanged plan is not announced again on every poll.

## Decision

We will add one module, `services.lifecycle_notifications`, whose functions stage
notifications and never commit. Each source service calls it inside its own transaction.
Every action gets one stable source key: the change request id, the safety review id,
the confirmation time, the completion's event id, and for a return to planning its cause
and source record. A plan ready for review is keyed on its fingerprint (ADR-0048), and is
checked when the Coordinator reads confirmation readiness, so polling an unchanged plan
collides with the first notification. Safety Officers are resolved from active role
holders.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| An outbox and a background sender | More moving parts than the inbox needs, and a rollback would still need cleaning up. |
| Announce a reviewable plan from every action that can change it | Five call sites in other stories' services, and easy to miss one. The fingerprint check on read catches all of them. |
| Copy the safety comment to the Organiser | SCRUM-79 keeps comments staff-side. The type already names the decision. |

## Consequences

**Good**
- A notification exists only if its action committed.
- Retries, polls and people in two roles never duplicate one.

**Bad / accepted trade-offs**
- A ready plan is announced when the Coordinator next opens the event, not the instant
  the last arrangement lands.

**What this makes harder to change later**
- A new trigger must pick a stable source key, or retries will notify twice.
