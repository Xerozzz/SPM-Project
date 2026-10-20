# ADR-0045: Link a replacement venue request to the arrangement it replaces

- **Status:** Proposed
- **Date:** 2026-10-20
- **Deciders:** Parikshit
- **Related stories:** SCRUM-116, SCRUM-133, SCRUM-81, SCRUM-89, SCRUM-78

## Context

When a closure (SCRUM-81) or a buffer change (SCRUM-89) leaves a confirmed booking or a
live hold needing attention, the assigned Coordinator has to find another venue for that
session. SCRUM-116 asks for this to reuse the existing venue request and approval flow,
not a second one, and for the old and new arrangements to stay traceably linked.
Adopting the replacement and retiring the original is SCRUM-133.

## Decision

- A replacement is an ordinary Pending venue request (SCRUM-78) with one new nullable
  column, `venue_bookings.replaces_booking_id`, pointing at the arrangement it replaces.
  Existing requests are simply not replacements.
- `POST /api/event-requests/{id}/venue-bookings` accepts an optional
  `replaces_booking_id`. The same access check, suitability and session rules apply.
- On top of those, `domain.venue_replacement` requires that the original:
  - belongs to the same event,
  - is a confirmed booking or a live hold,
  - currently needs attention, using the same derived check the Coordinator's list shows
    (SCRUM-89), so the button and the API never disagree,
  - has no replacement already in progress (pending, held or confirmed).
- The replacement keeps the original's session label and period. Only the venue changes.
- The original is not touched. A rejected or expired replacement leaves the original
  still needing attention, and another replacement can be requested (AC6).
- The event row lock that submission already takes serialises two replacements for the
  same arrangement.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A separate replacement table | The link is one value on a request that already exists. A table would duplicate the request store, which AC3 rules out. |
| Let the Coordinator change the session time in the replacement | Moving a session is a significant change (SCRUM-37). A replacement is about the venue only. |
| Allow several replacements in parallel | Venue Staff would approve two holds for one session, and SCRUM-133 would have to pick one. |

## Consequences

**Good**
- Replacement reuses search, suitability, approval and holds with no new flow.
- History and SCRUM-88 can follow the link in either direction.

**Bad / accepted trade-offs**
- Until SCRUM-133 lands, an approved replacement and its original both exist, and the
  Coordinator sees both.
