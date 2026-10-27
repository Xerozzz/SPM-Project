# ADR-0065: Equipment entries in the event history

- **Status:** Proposed
- **Date:** 2026-10-27
- **Deciders:** Sheryl, whole team at review
- **Related stories:** SCRUM-119 (AC6), SCRUM-43, SCRUM-53, SCRUM-115
- **Extends:** ADR-0062 (event history from retained source records), ADR-0064 (field changes)

## Context

SCRUM-119 AC6 asks for equipment requirement changes, reservations, releases and
reconsideration flags in the event history, with quantities. ADR-0064 set the rules for
before-and-after values; this records what the equipment records keep and what that
means for the entries.

- `equipment_requirement_changes` (SCRUM-43 AC8) keeps who, when, the action, and old and
  new quantity and technical requirements. The requirement carried across from the
  organiser's choice at approval is deliberately written with no change row.
- `equipment_reservations` (SCRUM-53) keeps the quantity, who reserved it and when. A
  release keeps who and when, and today only a whole-event cancellation (SCRUM-115)
  releases. A flag for reconsideration (ADR-0033) is a `flagged_at` time set by the
  requirement change that caused it, with no actor, and only the first flag is kept.
- No code on main mentions SCRUM-117; the only reconsideration flag is the one above.

## Decision

We will add two readers. A requirement change is one entry, its action from the row, with
exactly `quantity` and `technical_requirements` in `changes`, both sides as stored. A
reservation gives up to three entries, reserved, flagged and released, each with the
equipment type and quantity; a flag has no actor and is shown as the system. The new
actions are appended after ADR-0064's, with requirement changes ranked before a flag so
the change and the flag it raised in one commit read in cause-then-effect order.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Attribute a flag to the person whose change raised it, by matching the time | Not recorded on the flag; matching timestamps is inference, which ADR-0062 rules out |
| Show an "added" entry for the requirement seeded at approval | No change row exists, so the entry would be invented; the approval entry already marks that moment |
| Hide releases made by a whole-event cancellation until SCRUM-120 | Each is the reservation's own recorded change; the decision ADR-0064 made for bookings applies |

## Consequences

**Good**
- Equipment entries follow the same access, privacy, ordering and read-only rules with no
  change to the route or the timeline.

**Bad / accepted trade-offs**
- **New disclosure to the owner and Leads:** each reservation's Technical Support member
  and time. Through VIEW they saw only the total reserved and whether any was flagged.
  Requirement changes, including technical requirements text, were already readable by
  them, so those disclose nothing new.
- A flag shows as "System", at its first time only; a later change to the same
  requirement does not flag the reservation again.
- The seeded requirement has no "added" entry.

**What this makes harder to change later**
- If flags or seeding gain an actor or a change row, the readers can show it without any
  change to the entries' shape.
