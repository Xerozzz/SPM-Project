# ADR-0048: Record a safety decision against a fingerprint of the plan it judged

- **Status:** Proposed
- **Date:** 2026-10-21
- **Deciders:** Lee Yi Terng
- **Related stories:** SCRUM-79, SCRUM-110, SCRUM-111, SCRUM-43, SCRUM-44, SCRUM-53

## Context

SCRUM-79 puts a Safety Officer between planning and confirmation: they read an event's
plan and approve it, reject it, or ask for changes. The plan is not one record. It is the
event's attendance, accessibility and layout needs, its venue arrangements (several, since
SCRUM-111 gave each session its own period) and its equipment requirements with whatever
Technical Support have reserved against them. Every one of those can change while the
Officer is reading, and most of them are maintained by somebody else.

AC7 asks that a decision apply to "the plan version it was taken against". Nothing in the
schema has a plan version, because nothing in the schema has a plan: it is assembled at
read time from four tables. Without one, an approval saved at 10:04 silently covers
whatever the plan became at 10:03, which is the opposite of what a safety sign-off is for.

AC2 adds that a review cannot begin until the plan is arranged: venues actually held,
equipment assessed and reserved. Those prerequisites are maintained by Venue Staff and
Technical Support, so they can break between the Officer loading the screen and deciding.

## Decision

- A decision is stored with a **SHA-256 fingerprint of the plan**: a canonical JSON
  rendering of exactly the fields that bear on safety, each collection sorted by id. The
  Officer's screen sends back the fingerprint it was showing, and the API recomputes the
  plan and refuses the decision if the two differ.
- The fingerprint covers only what could change the answer. The event's name and purpose
  are not in it, so a rename does not invalidate a sound approval.
- **AC2's prerequisites are refusals, and they are checked again when the decision is
  saved**, not trusted from the read.
- **An event's plan is its standing arrangements only.** Rejected, cancelled and swept
  bookings are history the event keeps (SCRUM-40, ADR-0030) and are left out, matching
  what the equipment side already does with removed requirements.
- **A decision writes one row and changes nothing else.** It does not confirm the event
  (AC8) and does not move it out of planning (AC5). What the Coordinator still owes is
  read from the newest decision rather than stored as a flag.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| `max(updated_at)` across the contributing rows as the version | Fragile in both directions: it misses a deletion entirely, and a touch that changes nothing safety-relevant invalidates a sound approval. It also depends on every future writer remembering to bump a timestamp. |
| A version counter on the event, bumped by every writer | Spreads the safety rule across venue, equipment and reservation code, where nobody changing those has any reason to think about safety. The fingerprint needs nothing from them. |
| Snapshot the whole plan into the decision row | Stores the same venue and equipment data a second time, with no rule keeping the copy honest. The fingerprint answers "has it moved?", which is the only question AC7 asks. |
| Treat AC2's prerequisites as warnings the Officer may override | A plan half of which no venue has agreed to is not a thing anyone can judge the safety of. An override would make an approval mean less than it appears to. |
| Hide events that are not ready from the worklist | The Officer then cannot tell an event that is not ready from one that does not exist, and has no way to see what a Coordinator still owes them. |
| Have approval confirm the event | SCRUM-110 made confirmation the venue's decision, not a side effect of someone else's. AC8 says so explicitly. |

## Consequences

**Good**
- An approval provably refers to a plan somebody read. If anything moved, the Officer is
  told to read it again rather than quietly authorising something else.
- The rule is one pure function over a snapshot, so the whole of AC2 and AC7 is unit
  testable without a database.
- Nothing else in the codebase has to know safety review exists.

**Bad / accepted trade-offs**
- Any change to a safety-relevant field invalidates a pending decision, including one
  that makes the plan safer. The Officer re-reads and decides again; we preferred that to
  judging which changes are material.
- The fingerprint is opaque. "The plan changed" cannot yet say *what* changed, only that
  it did.
- The client has to avoid refreshing the plan behind the Officer's back, or it defeats
  the check from its own side. The screen disables refetch-on-focus for this reason.

**What this makes harder to change later**
- Adding a field to the plan changes every fingerprint, so decisions in flight at deploy
  time are refused once. Harmless, but worth knowing before a release.

## Notes

The "standing arrangements only" half came out of arranging a real event through the
running stack: a single rejected venue request made the plan permanently unreviewable,
because the rejected row is kept forever and nobody can clear it.

### An open dependency, for whoever builds confirmation

Customer Clarification 3, which the sheet says takes precedence where the clarifications
differ, answers the confirmation question twice and both times the same way:

> The Event Coordinator marks the event Confirmed only after required venue and technical
> approvals **and the Safety Officer's operational safety approval** are complete. An
> event cannot proceed to preparation before safety approval.

> All event-specific essential arrangements [...] must be approved. The Safety Officer
> must then approve the operational safety check; the Coordinator marks the event
> Confirmed after all approvals are complete.

That gate is not in this change, and it cannot be: nothing in the codebase sets an event
to `CONFIRMED`. `domain/event_status.py` says so outright — the transition into it "stays
a later story's to add". So AC8 holds trivially today, and the decision recorded here is
the record that story has to check before it lets a Coordinator confirm. Until it lands,
a safety approval is a judgement nobody downstream consults.
