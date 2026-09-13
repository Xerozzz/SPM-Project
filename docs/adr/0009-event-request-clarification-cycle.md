# ADR-0009: Keep clarification requests in the event-request review lifecycle

- **Status:** Proposed
- **Date:** 2026-09-13
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-30 (request clarification), SCRUM-31 (review and decide)

## Context

A coordinator may need more information or an amendment before deciding a submitted event
request. This is neither rejection nor approval: the organiser must be able to respond on the
same request, and the request must remain recognisably under review.

## Decision

We will use `clarification_requested` as an explicit event-request status, with transitions
`submitted -> clarification_requested -> submitted`. The request stores the coordinator,
timestamp, and free-text clarification request; these values clear on resubmission.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Treat clarification as rejection | It falsely records a decision and makes the organiser's outcome misleading. |
| Leave status as submitted | The organiser cannot tell whether action is required, and the coordinator queue has no clear lifecycle state. |
| Create a separate request row | It breaks the requirement to amend and respond on the same event request. |

## Consequences

**Good**
- The organiser receives a clear, accountable amendment request and can resubmit the same ID.
- Coordinator review queues include only requests ready for a decision.

**Bad / accepted trade-offs**
- The current request stores only the latest clarification, not a conversation history.

**What this makes harder to change later**
- A threaded discussion needs a new message/audit model and migration.
