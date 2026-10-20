# ADR-0043: Deciding a change request applies the event fields and flags arrangements

- **Status:** Proposed
- **Date:** 2026-10-20
- **Deciders:** Parikshit
- **Related stories:** SCRUM-47, SCRUM-37, SCRUM-79, SCRUM-80, SCRUM-113

## Context

SCRUM-37 stores an Organiser's proposal as a pending change request, with one item per
changed value and the value it would replace (ADR-0041). SCRUM-47 lets the assigned
Coordinator approve or reject it. Approval has to apply the change without overwriting
newer data (AC2), without silently moving confirmed venue bookings or equipment
reservations (AC4, AC8), and either completely or not at all (AC9).

Venue bookings and equipment reservations have their own approval flows, owned by Venue
Staff and Technical Support. The safety review (SCRUM-79), manual reconfirmation
(SCRUM-80) and registration suspension (SCRUM-113) are not merged yet.

## Decision

`POST /api/event-requests/{id}/change-requests/{change_id}/decision` takes
`{decision: approve | reject, note}`. Only the current assigned Coordinator may call it,
through a new `EventAccess.DECIDE_CHANGE_REQUEST` mode, and the service checks again on
the locked event row.

- **Stale check by value, not by version.** Each item's recorded current value is compared
  with the live event, session or equipment line. Any difference, or a record that no
  longer exists, refuses the approval with 409 and the request stays pending. The event's
  `updated_at` is kept for audit but not compared, because it also changes for unrelated
  edits such as a coordinator reassignment or an ordinary text update.
- **Re-validated against today's rules.** The proposal is rebuilt from its items and run
  through the SCRUM-37 rules again, so a start time that has since passed is refused.
- **Only the event's own fields are applied.** Session and equipment items are marked
  `needs_replanning` on the item and left for the venue and equipment flows. Nothing moves
  a booking or a reservation.
- **A Confirmed event returns to Approved** (planning) through a new `replan` transition in
  the status machine, which only a Confirmed event can take.
- **Decided once.** The request row is locked for the decision, and a decided request
  refuses another decision with 409, so changes cannot be applied twice.
- Rejection records the note and changes nothing on the event.

Everything happens in one transaction. Any refusal rolls back, leaving the plan and the
request as they were.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Compare the event `updated_at` with the snapshot | Any edit to the event, even a reassignment, would make every pending request stale. |
| Apply session periods and equipment quantities directly | That would move a confirmed booking or change a reserved quantity without the people who approved them, which AC8 forbids. |
| Delete the request on rejection | The decision and its reason are part of the event's history (SCRUM-120 will read them). |

## Consequences

**Good**
- A decision never overwrites newer data and never touches venue or equipment
  commitments.
- The items marked `needs_replanning` are the list later stories act on.

**Bad / accepted trade-offs**
- An approved session or equipment change does not happen by itself. The Coordinator still
  has to raise it through the venue or equipment flow. Part 2 of SCRUM-47 will add those
  operations once SCRUM-79, SCRUM-80 and SCRUM-113 are merged.
- Invalidating a previous safety approval and suspending registration (AC5, AC7) wait for
  those stories.

**What this makes harder to change later**
- Applying arrangements automatically would need a new outcome value and its own ADR.
