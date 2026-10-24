# ADR-0057: Adopt a replacement by cancelling the original through SCRUM-109

- **Status:** Proposed
- **Date:** 2026-10-24
- **Deciders:** Parikshit
- **Related stories:** SCRUM-133, SCRUM-116, SCRUM-109, SCRUM-110, SCRUM-79, SCRUM-80

## Context

SCRUM-116 lets the Coordinator request a replacement venue for an affected booking, linked
by `replaces_booking_id` (ADR-0045). The original stayed as it was until someone adopts
the replacement. SCRUM-109 now cancels one arrangement of an event in planning, with a
staged step (`stage_cancellation`) built for callers that commit once. Adoption needs a
record of who did it and when, and adopting twice must change nothing.

## Decision

We will add `adopted_by_id` and `adopted_at` to the replacement row. One endpoint,
`POST .../venue-bookings/{id}/adopt`, for the current assigned Coordinator (the SCRUM-109
access mode). It locks the event and the replacement, checks the replacement is an
approved hold or a confirmed booking, cancels the original with `stage_cancellation`, sets
the adoption fields and commits once. An already adopted replacement is returned as it is.
The event's status is not touched.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Mark the original "replaced" with a new status | SCRUM-109 already has Cancelled with who, when and why. A second retired status would need its own rules in every check that reads status. |
| Adopt automatically when Venue Staff approve | AC1 asks for an explicit adoption by the Coordinator. |
| A separate adoption table | One adoption per replacement, so two columns on the row are enough and keep the link in one place. |
| Reconfirm the event on adoption | AC2 says reconfirmation goes through safety review and SCRUM-80. |

## Consequences

**Good**
- Cancellation rules live in one place. A Confirmed event or an original that is no
  longer live is refused the same way SCRUM-109 refuses it.
- Old and new stay linked, and the original keeps its full history.

**Bad / accepted trade-offs**
- A Confirmed event must go back to planning first (SCRUM-130 or SCRUM-132) before a
  replacement can be adopted.

**What this makes harder to change later**
- Any other way of retiring an original should also go through `stage_cancellation`.
