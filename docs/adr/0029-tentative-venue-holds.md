# ADR-0029: Place a tentative venue hold on a pending booking request

- **Status:** Proposed
- **Date:** 2026-10-14
- **Deciders:** Parikshit
- **Related stories:** SCRUM-83, SCRUM-107, SCRUM-108, SCRUM-78, SCRUM-73, SCRUM-74

## Context

Week 7 change 4 says Venue Staff sometimes hold a venue while an Event Coordinator
finalises arrangements. A hold must have an expiry, must not be treated as a confirmed
booking, and must stop affecting availability once it expires. SCRUM-83 covers placing
a hold, showing it as Tentative and making it block overlapping requests. SCRUM-107
covers confirming it through the normal approval, and SCRUM-108 covers expiry and the
Coordinator's notification.

ADR-0026 (SCRUM-78) deliberately left pending requests as requests that block nothing,
and said holds must define their occupancy and expiry explicitly rather than treating
every pending request as a hold. ADR-0002 says overlap is prevented by the database.

## Decision

We will let Venue Staff put a **pending venue booking request** on a tentative hold.
The row moves from `pending` to a new status `tentative`, and records `expires_at`,
`held_by_id` and `held_at` (migration 0021). The request already carries the venue, the
event, its period and the event's assigned Coordinator, so the hold is for all of them.

A tentative hold occupies the venue the way a confirmed booking does. `BLOCKING_STATUSES`
in `domain/venue_search.py` is `{confirmed, tentative}`, and approval, venue search,
the availability check and the calendar all read it. The ADR-0002 exclusion constraint
is widened to the same two statuses, so two overlapping holds, or a hold and a
confirmed booking, cannot both be written even if the friendly check races.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A separate `venue_holds` table | Every conflict query, the calendar and the overlap constraint read `venue_bookings`. A second table needs each of them extended, and a constraint cannot span two tables, so hold-against-booking overlap would rest on an application check that races. |
| Let Venue Staff hold any venue for any event | Needs a new list of events for Venue Staff and a way to turn the hold into a booking later. Holding a request reuses both: the request names the event and venue, and SCRUM-107 can confirm it through the existing approve route, which is "the normal booking flow". |
| Treat every pending request as a hold | Rejected by ADR-0026: a pending request would then block other events without anyone choosing to hold the venue. |
| Make expiry part of the blocking rule now (`expires_at > now`) | The overlap constraint cannot read the clock. The app and the database would disagree about an expired hold until its status changed, so expiry is done by moving the status (SCRUM-108). |

## Consequences

**Good**
- One rule for what occupies a venue, read everywhere, and backed by the constraint.
- Rejected, cancelled and pending rows behave exactly as before.

**Bad / accepted trade-offs**
- Until SCRUM-108 lands, a hold keeps blocking after its `expires_at`. It is shown with
  its expiry, so Venue Staff can see it has run out.
- A hold can only be placed on a request a Coordinator has already made.
- SCRUM-73 and SCRUM-89 tests that said "everything except confirmed does not block" now
  leave out tentative too.

**What this makes harder to change later**
- A hold that is not tied to a request would need a different way to name its event and
  Coordinator.

## Notes

The expiry must be in the future and not after the event starts
(`domain/venue_hold.py`). A hold is not a decision: `decided_by_id` and `decided_at` stay
empty until the request is approved or rejected.
