# ADR-0073: Separate coordinator review summaries and details

- **Status:** Proposed
- **Date:** 2026-10-30
- **Related stories:** SCRUM-104, SCRUM-38, SCRUM-80
- **Extends:** ADR-0071

## Context

The Coordinator's review queue expands all event-management controls in every event card.
The planning, booking, confirmation and registration workflows make the queue difficult to scan.

## Decision

The review queue will show compact cards grouped into Submitted, Approved and Confirmed tabs.
Each card shows its lifecycle status, schedule and venue requirement. View details opens one
event's existing coordinator workspace; returning preserves the selected tab. Existing API
permissions and status permits remain authoritative.

## Consequences

- Coordinators can identify the next lifecycle stage before opening a workflow.
- Each management workflow takes one additional click and cannot be linked directly.
