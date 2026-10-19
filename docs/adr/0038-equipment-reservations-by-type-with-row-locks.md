# ADR-0038: Reserve equipment by type, serialised with catalogue row locks

- **Status:** Proposed
- **Date:** 2026-10-19
- **Deciders:** Divyaanshu Das
- **Related stories:** SCRUM-53 (reserve equipment), SCRUM-52 (check availability),
  SCRUM-43 AC6 (flag a changed requirement's reservation)

## Context

SCRUM-53 asks Technical Support Staff to reserve equipment so the same limited stock is
not committed to overlapping events. ADR-0033 left two questions for it: what a
reservation is reserved *against*, given that requirements name a type rather than a
catalogue entry; and how to stop two reservations both taking the last unit.

AGENTS.md §3 says equipment conflicts are prevented by the database with `tstzrange` and
`EXCLUDE USING gist`, as venue bookings are (ADR-0002, ADR-0017). That works for a venue
because a venue is one thing that is either free or not. Equipment is a quantity: five
projectors can serve three overlapping events at once, so whether a reservation conflicts
depends on the **sum** of everything overlapping it. An exclusion constraint compares
rows in pairs and cannot express a sum.

## Decision

**`equipment_reservations` holds one row per act of reserving**: a quantity of one type,
for one requirement, over the event's window copied in at that moment, with who made it.
Topping up a partial reservation adds a second row. `released_at` and `flagged_at` exist
for Event Change Management and SCRUM-43 AC6, and nothing sets them yet.

**The reservation is against a type, not a catalogue entry**, because that is what a
requirement asks for (ADR-0024) and what SCRUM-52 counts stock across.

**Reserving takes `SELECT … FOR UPDATE` on every catalogue entry of the type before
counting what is free**, and commits the reservation in the same transaction. A second
reservation of that type waits for the first to commit, then counts again and sees it.
Entries are locked in id order so no two callers deadlock. A refusal raises without
writing, and the request's session closing rolls the transaction back and drops the locks.

**The reservation state is derived** from the requirement's quantity and the sum of its
live reservations, never stored, so it cannot disagree with the rows it summarises.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Exclusion constraint, as for venues | Cannot express "the sum of overlapping quantities is at most stock" |
| One reservation row per unit, with an exclusion constraint per unit slot | Needs numbered units the catalogue does not have; reserving ten is ten rows |
| Application check with no lock | Two reservations read the same free quantity and both commit; the exact race ADR-0002 exists to prevent |
| `SERIALIZABLE` isolation for the reservation | Correct, but a refusal surfaces as a serialisation failure the caller must retry, and no other code here runs at that level |
| Postgres advisory lock keyed on the type | Works, but the key is a hash of a string, and it does not stop a catalogue edit changing stock mid-reservation the way a row lock does |
| Join the event's window instead of copying it | A reservation would silently move with the event; whether it still stands is Event Change Management's decision |
| Store a reservation state column on the requirement | A second copy of a number that can be derived, which would drift the first time someone forgot to update it |

## Consequences

**Good**
- Two Technical Support Staff reserving the last units of a type cannot both succeed.
- SCRUM-52's availability check needed no change at its call site; it now sees real
  reservations.
- Each row says who committed how much and when, so the history of a requirement's
  reservations needs no separate audit table.

**Bad / accepted trade-offs**
- **This is the one place equipment conflicts are not enforced by a database constraint**,
  contrary to AGENTS.md §3. Correctness depends on every writer of `equipment_reservations`
  taking the lock first. Today there is one writer, `services.equipment_reservations`.
- A type with no catalogue entries has nothing to lock. That is safe only because such a
  type has no stock, so every reservation of it is refused.
- Reservations of one type queue behind each other, and so do catalogue edits to it. At
  this system's scale that is milliseconds.
- A reservation does not lock the event, so an event moved out of planning at the same
  instant can still gain a reservation. Event Change Management will need to handle that.
- Removing or changing a requirement leaves its reservations live. Stock held for a
  removed line is still counted against the event (`held_by_event`) so it is not handed
  out twice, but nothing releases it until a later story does.

**What this makes harder to change later**
- Per-location allocation would need a reservation per entry rather than per type.
