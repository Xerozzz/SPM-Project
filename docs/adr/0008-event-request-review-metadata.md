# ADR-0008: Store event-request review metadata on the request

- **Status:** Proposed
- **Date:** 2026-09-14
- **Deciders:** Wei Lin
- **Related stories:** SCRUM-28, SCRUM-30, SCRUM-31

## Context

Event requests need to retain the information associated with coordinator review: who made a
review decision, when the decision was made, and why a request was rejected. The clarification
workflow also needs to retain who requested clarification, when it was requested, and the
question sent to the organiser.

These values are part of the event-request record and must remain available after the review or
clarification action. Existing requests must continue to work before those actions occur, so the
new fields need to be optional. The status transition rules remain governed by ADR-0006 and the
domain status machine.

## Decision

We will store review-decision and clarification metadata as nullable columns on `event_requests`.
User references will use foreign keys to `users`, and the actor-reference columns will be indexed.
The timestamps will use timezone-aware database columns.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Store review and clarification records in separate tables | The current workflows need a small set of attributes tied directly to one event request; separate tables would add joins and lifecycle management before that complexity is required. |
| Store the metadata only in application logs | Logs are not the event request's durable data and are not a reliable API or UI data source. |
| Make the new fields non-nullable | Existing requests have not yet been reviewed or sent for clarification, so those values do not exist at creation time. |

## Consequences

**Good**
- The request keeps a durable audit trail for review and clarification actors, timestamps, and text.
- Existing drafts and submitted requests remain valid because the new fields are nullable.
- Foreign keys prevent references to users that do not exist.

**Bad / accepted trade-offs**
- Nullable columns allow incomplete combinations until the review and clarification services enforce their workflow rules.
- The event-request row grows as future review metadata is added.

**What this makes harder to change later**
- Moving review history to a full event log or separate history table will require a migration and API changes.

## Notes

- Migration `0004_add_event_request_review_decision.py` adds decision metadata.
- Migration `0005_add_event_request_clarifications.py` adds clarification metadata.
- ADR-0006 remains the source of truth for legal status transitions.
