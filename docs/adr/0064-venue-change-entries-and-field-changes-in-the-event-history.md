# ADR-0064: Venue change entries, and before-and-after values as whitelisted field changes

- **Status:** Proposed
- **Date:** 2026-10-27
- **Deciders:** Sheryl, whole team at review
- **Related stories:** SCRUM-119 (this PR: venue entries; equipment entries follow), SCRUM-120
- **Extends:** ADR-0062 (event history from retained source records)

## Context

SCRUM-119 adds venue and equipment changes to the event history that ADR-0062 builds from
existing records. This first part covers the venue changes: a single arrangement
cancelled (SCRUM-109), a replacement requested and adopted (SCRUM-116, SCRUM-133), the
session period on every venue entry (SCRUM-111), a venue buffer change that caught the
event's bookings out (SCRUM-89), and an update to a hold's expiry (SCRUM-121).

Two of those carry values before and after (buffers here; equipment quantities and
technical requirements next; change requests in SCRUM-120). The history is shown to the
owner and Leads as well as the assignee, so whatever shape carries those values must not
let a field nobody chose for them reach the screen.

What the records keep:

- **Cancellation:** `venue_bookings.cancelled_by_id` / `cancelled_at` / `cancellation_reason`,
  required together by a check constraint. A whole-event cancellation (SCRUM-115) cancels
  each booking through the same writer, with the event's reason.
- **Replacement:** `replaces_booking_id` on the replacement, kept after either side is
  decided, and `adopted_by_id` / `adopted_at` on it. Adoption cancels the original through
  SCRUM-109 in the same transaction, with a fixed reason.
- **Session period:** `start_at` / `end_at` on the booking. SCRUM-88 showed only the label.
- **Buffer change:** `venue_buffer_changes` keeps both old and new setup and turnaround,
  who and when, and `flagged_booking_ids`: the bookings the change made problematic.
- **Expiry update:** `update_hold_expiry` overwrites `venue_bookings.expires_at` and
  writes nothing else. The old expiry, who changed it and when are not stored anywhere.

## Decision

We will add readers for the venue changes and carry before-and-after values as a list of
field changes, `changes: [{field, label, old, new}]`, under two rules:

1. **Each reader whitelists its fields.** It names the fields it emits; none copies a row
   or compares every column. The buffer reader emits exactly `setup_minutes` and
   `turnaround_minutes`. Each reader has a unit test asserting the exact set of field
   names it can emit, so adding one is a deliberate change to that test.
2. **Each change carries its display label** ("Setup time (minutes)"), set by the reader.
   The UI shows `label: old → new` and never a column name. Values are text, and a
   missing side is null, shown as "—".

Adopting a replacement is shown as two linked entries, each its record's own action:
"Replacement adopted" on the replacement and "Arrangement cancelled" on the original, at
the same time, each naming the other arrangement. The original's link is read from the
adopted replacement's `replaces_booking_id`. Every cancellation is shown, including those
a whole-event cancellation made; SCRUM-120 will add the event-level entry beside them.

A buffer change is shown on an event only when its `flagged_booking_ids` include one of
the event's bookings, and the entry lists only those, never another event's.

The new actions are appended after ADR-0062's, so the existing tie-breaker order is
unchanged; adoption ranks before cancellation because it causes it.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Typed fields per value (`old_setup_minutes`, `new_quantity`, ...) | The entry schema and the UI would grow with every source; SCRUM-120's change requests alone would add many |
| A generic diff of every changed column | A field nobody reviewed for the audience could reach the owner; rule 1 exists to prevent exactly that |
| Column names as labels | Not readable, and it ties the screen to the database |
| One entry for an adoption, hiding the original's cancellation | Needs matching on the fixed reason text, which is fragile; the cancellation is a real change to another record |
| Hide booking cancellations made by a whole-event cancellation until SCRUM-120 | They are complete records of each booking's own change, and hiding them needs inferring the cause from equal timestamps |
| Reconstruct an expiry update from the current expiry | The old value, actor and time are not stored; anything shown would be invented |

## Consequences

**Good**
- The timeline, ordering, route and access rules are unchanged; access and the SCRUM-106
  note filter apply to the new entries as they are.
- One renderer shows any before-and-after values, and no source can leak a field by default.

**Bad / accepted trade-offs**
- **Gap, AC2 (moved to SCRUM-136):** an update to a hold's expiry has no entry, because nothing
  records it. Recording it needs a schema change (the old expiry, who and when) that this
  story does not make. Until then the existing "Tentative hold placed … Held until X"
  entry shows the *latest* expiry, so an updated hold reads as if it was placed with it.
- **Gap, AC5:** a buffer change that touched the event's venue without making any of its
  bookings problematic has no link to the event, so it is not shown.
- A booking cancelled after it was confirmed still shows no confirmation (ADR-0062).
- **New disclosure to the owner and Leads:** cancellation reasons, which only the assigned
  Coordinator saw, and buffer changes with the Venue Staff member's email.

**What this makes harder to change later**
- `changes` is a contract every later source uses; a reader adding a field is a reviewed
  change to its whitelist test.

## Notes

- Equipment entries (SCRUM-119 AC6) follow in a second PR under the same rules.
