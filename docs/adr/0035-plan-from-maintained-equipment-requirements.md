# ADR-0035: Plan from the maintained equipment requirements, not the organiser's string

- **Status:** Proposed
- **Date:** 2026-10-18
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-43, SCRUM-38, SCRUM-56, SCRUM-90

## Context

ADR-0033 created `event_equipment_requirements`, one row per equipment type per event,
and left `event_requests.equipment_requirement` in place as the organiser's captured
choice. It named the cost of that in its own consequences:

> **There are now two places an event's equipment appears.** `equipment_requirement` is
> where the organiser's choice is captured and still what venue suitability compares
> against; these rows are what is planned from. They agree at approval and can diverge
> afterwards, because a Coordinator maintaining requirements does not write back to the
> organiser's field.

This is that follow-up. The divergence is not hypothetical: a Coordinator adding,
changing or removing a requirement is the whole of SCRUM-43, and the moment they do,
`equipment_requirement` is stale. Venue suitability was still scoring against it.

It was also scoring against *one* type. The column holds a single string, so an event
needing a projector, a microphone and a PA system was judged on whichever one the
organiser happened to pick.

## Decision

**`services.venue_bookings.evaluate` reads the maintained requirement rows.** Venue
suitability now asks `equipment_requirements.list_for_event` what the event needs, and
judges the venue against all of the live requirements rather than one stale string.

**`event_requests.equipment_requirement` stays, and keeps its meaning.** It is what the
organiser submitted. It is still validated against the catalogue (ADR-0024), still what
the organiser's own form reads and writes, and still the seed that becomes the event's
first maintained requirement at approval (ADR-0033). Nothing writes back to it, and
nothing reads it for planning any more.

**`EQUIPMENT_REQUIREMENT_FACILITIES` stays as the bridge between two vocabularies.**
Equipment types and venue facilities are separate lists (ADR-0031, ADR-0032). A venue
offers a fixed projector; it does not offer the portable things that arrive from a store
room. A requirement with no counterpart in that map is not scored against the venue.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Fall back to `equipment_requirement` when an event has no requirement rows | Silent, and wrong in the only case it fires. Approval seeds the first row, so an approved event with no rows is an event whose organiser asked for nothing. A fallback would turn "nothing is required" into "the organiser's old choice is required". |
| Drop `equipment_requirement` and migrate everything to rows | Supersedes ADR-0024's storage decision, rewrites the organiser's form from SCRUM-90, and loses the original submission. The ticket asks for the submission to be preserved as history. A bigger change with no extra value for planning. |
| Write the Coordinator's changes back to the string | Two writers for one column, and the column cannot hold several types or quantities. It would also make the organiser's submission unrecoverable. |
| Compare every requirement type against venue facilities, unmapped ones included | Every event needing anything portable would warn about every venue. The two vocabularies are not the same list, which is why the map exists. |

## Consequences

**Good**

- Suitability answers the question that is actually being asked: can this venue host what
  this event currently needs, all of it.
- The Coordinator's work takes effect where it matters. Before this, maintaining
  requirements changed nothing about how venues were judged.
- The organiser's submission survives as history, which is what makes a later "what did
  they originally ask for" answerable.

**Bad / accepted trade-offs**

- **A requirement type with no entry in `EQUIPMENT_REQUIREMENT_FACILITIES` is not scored
  against the venue at all.** It is neither a match nor a missing facility. That is the
  same silence the code had before for every type outside the map, and the same silence
  `venue_requirement` already has, but it is silence: an event needing a smoke machine
  gets no venue warning either way. Mapping the catalogue to venue facilities properly is
  a question for whoever owns venue facilities, not this change.
- **Two representations still exist.** This removes the second *reader*, not the second
  copy. `equipment_requirement` can still drift from the rows; it just no longer matters
  for planning.

**What this makes harder to change later**

- Anything that wants to know "what does this event need" must read the rows. The string
  is now unambiguously the submission record, and reading it for a current answer is a
  bug rather than a shortcut.

## Notes

- Does **not** supersede ADR-0024: the column and its catalogue validation are unchanged.
  This narrows what reads it, which ADR-0033 anticipated.
- `evaluate` now takes a database session it previously only passed through. The unit
  tests fake `list_for_event` rather than a session.
- `tests/integration/test_submit_venue_booking.approved_event` now seeds the first
  requirement through `equipment_requirements.seed_from_event`, the same function
  approval uses. Without it the helper produced an event with an equipment string and no
  rows, which approval cannot produce, and tests were asserting against that state.
