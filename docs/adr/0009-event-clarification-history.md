# ADR-0009: Retain event clarification as a message history

- **Status:** Proposed
- **Date:** 2026-09-17
- **Deciders:** SCRUM-30 author, whole team at review
- **Related stories:** SCRUM-30

## Context

Coordinators need to request clarification on submitted event requests, and organisers need to
respond without unlocking or directly changing submitted event details. The conversation must
remain visible with its authors and timestamps. Event requests receive a coordinator assignment
when first submitted under SCRUM-34.

## Decision

We will store coordinator requests and organiser responses in one chronological
`event_clarifications` table. Shared `require_event_access(...)` dependencies will allow the
creating organiser and assigned coordinator to contribute only after submission. Other
coordinators retain read-only access to submitted requests for review and planning.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Add a clarification event status | Clarification is a conversation within review and must not change lifecycle status |
| Separate request and response tables | Both records have the same event, author, text and timestamp shape and belong in one history |
| Add a second clarification-specific assignment | SCRUM-34 already provides the event's coordinator assignment |

## Consequences

**Good**
- The complete conversation is retained in one deterministic history.
- Submitted requests remain locked and no clarification action changes status.

**Bad / accepted trade-offs**
- Unassigned coordinators can inspect submitted review information but cannot contribute.

**What this makes harder to change later**
- Reassignment must immediately transfer clarification-action permission to the new assignee.
