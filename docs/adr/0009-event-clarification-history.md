# ADR-0009: Retain event clarification as a message history

- **Status:** Proposed
- **Date:** 2026-09-17
- **Deciders:** SCRUM-30 author, whole team at review
- **Related stories:** SCRUM-30

## Context

Coordinators need to request clarification on submitted event requests, and organisers need to
respond without unlocking or directly changing submitted event details. The conversation must
remain visible with its authors and timestamps. Coordinator assignment is not implemented on
this branch, so there is no assignment relationship to enforce yet.

## Decision

We will store coordinator requests and organiser responses in one chronological
`event_clarifications` table. Shared `require_event_access(...)` dependencies will allow the
creating organiser and coordinators to participate only after submission; until assignment is
available, any coordinator may access a submitted request's clarification history.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Add a clarification event status | Clarification is a conversation within review and must not change lifecycle status |
| Separate request and response tables | Both records have the same event, author, text and timestamp shape and belong in one history |
| Add coordinator assignment in this story | Assignment belongs to another story and inventing it here would create a conflicting model |

## Consequences

**Good**
- The complete conversation is retained in one deterministic history.
- Submitted requests remain locked and no clarification action changes status.

**Bad / accepted trade-offs**
- All coordinators can access submitted clarification threads until assignment is implemented.

**What this makes harder to change later**
- Once coordinator assignment is merged, clarification creation must be restricted to the
  assigned coordinator. Other coordinators may retain read-only visibility according to the
  assignment story.
