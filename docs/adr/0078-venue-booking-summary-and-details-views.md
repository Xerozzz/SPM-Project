# ADR-0078: Review venue bookings through summaries and a details view

- **Status:** Proposed
- **Date:** 2026-10-30
- **Deciders:** Sheryl (requested the Venue Staff improvements), whole team at review
- **Related stories:** SCRUM-40, SCRUM-75, SCRUM-110, SCRUM-121
- **Extends:** ADR-0018 (decisions), ADR-0029 (holds), ADR-0076 (hold and decision summaries)

## Context

Every booking request currently displays its full requirements and decision form.
The page automatically changes tabs when a status group becomes empty. The Approve
button gives little indication that its result is a tentative hold.

## Decision

Venue Staff will land on Booking Decisions. Compact summaries open one booking's existing
details and controls. The primary action reads Approve and place hold; session times and
hold expiry have separate labels. Decisions update the selected booking and confirmation,
while returning to the list preserves the chosen tab even when it is empty. Server-side
authorisation, conflict checks, expiry rules and endpoints remain unchanged.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Expand all forms in the list | Makes comparing bookings slow and visually crowded |
| Jump to another tab after a decision | Changes context when the user finishes the last request |
| Add separate detail URLs now | Requires wider navigation changes for this single-screen improvement |

## Consequences

**Good**
- Summaries make requests easier to scan and distinguish tentative holds from confirmations.
- Existing decision components, API calls and failure handling are retained.

**Bad / accepted trade-offs**
- Reviewing a request takes an extra click; a reload returns to the pending list.

**What this makes harder to change later**
- Shareable booking details will need the local selection integrated with URL navigation.
