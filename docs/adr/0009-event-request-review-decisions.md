# ADR-0009: Store the current event-request review decision on the request

- **Status:** Proposed
- **Date:** 2026-09-13
- **Deciders:** Wei Lin
- **Related stories:** SCRUM-31 (review and decide), SCRUM-35 (view status and allowed actions)

## Context

An Event Coordinator's approval or rejection needs an accountable coordinator and timestamp,
while an Event Organiser must see the current outcome and any rejection reason. A rejected
request is edited and resubmitted as the same request, so the current decision is replaced by
the later submission rather than creating a new event-request row.

## Decision

We will store `decided_by_id`, `decided_at`, and `rejection_reason` as nullable columns on
`event_requests`. The shared status machine controls `submitted -> approved | rejected` and
`rejected -> submitted`; resubmission clears the previous decision fields.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A separate decision-history table | The story needs only the current review outcome; it adds queries and UI with no acceptance-criterion benefit. |
| Put the coordinator and reason only in application logs | Organisers cannot see the outcome, and the decision is not durable application data. |
| Create a new event request after rejection | It breaks the requirement to amend and resubmit the same request. |

## Consequences

**Good**
- A request response contains its current outcome, decision time, coordinator, and rejection reason.
- The decision remains separate from venue, equipment, and registration workflows.

**Bad / accepted trade-offs**
- This is not an audit trail of superseded rejections; a future audit-history story needs a new table and ADR.

**What this makes harder to change later**
- Adding decision history requires a data migration, but current request reads remain simple.

## Notes

- Migration: `api/alembic/versions/0004_add_event_request_review_decision.py`.
