# ADR-0033: Make an event's equipment requirements records, with the organiser's choice as the first one

- **Status:** Proposed
- **Date:** 2026-10-16
- **Deciders:** Lee Yi Terng
- **Related stories:** SCRUM-43 (record equipment requirements), SCRUM-44 (review them),
  SCRUM-53 (reserve equipment), SCRUM-90 (select from the catalogue)

## Context

ADR-0024 kept `event_requests.equipment_requirement` as a single string naming a catalogue
type, rejected storing an id, and closed with:

> Allocating a specific item or quantity needs a new data model and decision record.

SCRUM-43 is where that bill comes due. It asks for a quantity per requirement (AC3), for
several requirements per event with no repeated type (AC4), for a review state that resets
when a requirement changes (AC5), for removed requirements to stay identifiable (AC7), and
for an audit trail (AC8). None of that fits in one nullable text column.

Its AC1 adds a constraint that shapes the whole thing: the requirements the organiser
captured "are the same records the assigned Coordinator maintains; they are not
re-entered." So the new model cannot simply start empty beside the old column.

## Decision

**`event_equipment_requirements` holds one row per equipment type per event**, with a
quantity, optional free-text technical detail, a review state and a soft-removal marker.
The type stays a string naming a catalogue type, as ADR-0024 decided, because an event
still asks for a kind of thing rather than a particular item in a particular room.

**Approval is the handoff.** Before approval the organiser owns the single type they
picked; at approval that type becomes the event's first requirement, with a quantity of
one. Migration 0023 does the same for events that already exist, **and only for approved
ones**, so the migration draws the line in the same place the application does. Backfilling
every status would have caused exactly the drift this ADR rejects below: an organiser can
still edit a draft, so the row and the string would disagree while both were live. Neither
path writes an audit row, because nobody performed those changes.

That point is chosen deliberately. Approval is where an event stops being a draft and
becomes the assigned Coordinator's to plan, which is exactly the boundary AC1 and AC2
describe. Seeding earlier would mean two places to keep in step while the organiser was
still editing; seeding later would mean a Coordinator opening an empty list and retyping
what the organiser had already chosen.

**The organiser's column stays**, and this table is what the Coordinator and Technical
Support Staff work from.

**Uniqueness is a partial index**, over live rows only. A removed requirement keeps its
row, so a plain unique constraint would make removal a one-way door for that type.

**An edit is judged without the catalogue.** Adding a requirement checks the type
against the active catalogue; changing one does not, and `validate_change` is not even
given the catalogue to check against. Re-checking would mean that deactivating the last
entry of a type froze every requirement already asking for it: the Coordinator would be
told to fix a field the PATCH schema does not accept, and their only way out would be to
delete the line. Whether a type can still be supplied is SCRUM-44's question.

**The review vocabulary is written down in full now** (`pending_review`, `available`,
`partially_available`, `unavailable`), although SCRUM-43 only ever sets the first. The
other three are the outcomes SCRUM-44's acceptance criteria name, so that story extends a
closed list rather than inventing a second one.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep the single string and add a quantity column beside it | One requirement per event forever. AC4 only makes sense with several |
| Store a catalogue entry id rather than a type | ADR-0024 rejected this and nothing has changed: an event needs two microphones, not the two in room 4-1 |
| Repoint the organiser's form and venue suitability at the new rows in this story | Four merged stories read `equipment_requirement`. Changing them all here would make the diff unreadable and put SCRUM-90's just-merged work at risk for no gain this story needs |
| Hard-delete a removed requirement | AC7 wants it identifiable in the history, which a deleted row cannot be |
| Seed the first requirement when the organiser submits | The organiser can still edit a submitted request, so the string and the row would drift apart while both were live |

## Consequences

**Good**
- A Coordinator maintaining requirements never retypes what the organiser asked for.
- One type is one line, enforced by the database for live rows, so "how many do we need"
  has one answer.
- Removal keeps the history, and the same type can be asked for again afterwards.
- SCRUM-44 inherits a review state it only has to transition, and SCRUM-53 inherits
  requirements it only has to reserve against.

**Bad / accepted trade-offs**
- **There are now two places an event's equipment appears.** `equipment_requirement` is
  where the organiser's choice is captured and still what venue suitability compares
  against; these rows are what is planned from. They agree at approval and can diverge
  afterwards, because a Coordinator maintaining requirements does not write back to the
  organiser's field. Consolidating them is a follow-up that supersedes ADR-0024's storage
  decision, touches SCRUM-56's suitability check and SCRUM-90's form, and deserves its own
  story rather than being smuggled into this one.
- The uniqueness rule is checked in the domain and enforced by the index, which is a
  read followed by a write. Two coordinators adding the same type at the same instant
  both pass the check, and the loser is turned back into the same refusal by catching the
  index violation, the way `repositories.equipment` already does.
- A quantity of one is assumed for every seeded requirement. It is the only honest reading
  of a field that never held a number, and it is wrong whenever the organiser wanted more.
- The type cannot be edited on an existing line. Moving a line to a different type is a
  removal and an addition, which keeps the history truthful at the cost of two clicks.

**What this makes harder to change later**
- Per-location allocation still needs the model ADR-0024 deferred and this one did not
  build. Reserving against a type rather than an entry is SCRUM-53's problem to solve.
- The divergence above gets more expensive the longer both representations are read.

## Open questions

- **AC6 has no subject yet.** It describes a requirement that already has an equipment
  reservation being changed or removed, and says the reservation is flagged rather than
  released. SCRUM-53 is what creates reservations and has not been built, so nothing here
  implements it. The flag should reuse whatever marker SCRUM-53 and SCRUM-44 settle on
  rather than a third one.
- **"Planning" in AC2 is APPROVED here.** The codebase already calls that phase planning
  (see the note on `ACTIVE_STATUSES`), and there is no Safety Officer flow to return an
  event to it, so the two names describe one status. Worth confirming with the PO rather
  than assuming it stays that way.
