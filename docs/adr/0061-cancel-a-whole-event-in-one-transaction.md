# ADR-0061: Cancel a whole event in one transaction, reusing each owner's staged operation

- **Status:** Proposed
- **Date:** 2026-10-25
- **Deciders:** Parikshit
- **Related stories:** SCRUM-115, SCRUM-109, SCRUM-110, SCRUM-53, SCRUM-113, SCRUM-134, SCRUM-50, SCRUM-135

## Context

Cancelling an event has to release everything it holds: venue requests, holds and
Confirmed bookings, equipment reservations, and live registrations. A failure must not
leave the event Cancelled while something it held still blocks availability, and a
repeat must not release or notify twice. Each of those records already has an owner
story, and the story says not to write a second copy of their cancel logic. SCRUM-109's
single-booking cancel refuses any event outside planning, because a Confirmed event
changes venue through SCRUM-118, so a whole-event cancel cannot call it as it is. The
Organiser can also ask for a cancellation, which the Coordinator applies or declines.

## Decision

We will add `cancelled` to the status machine as a terminal status, reached from
`submitted`, `approved` and `confirmed`. `cancelled_by_id`, `cancelled_at` and
`cancellation_reason` on the event record the action.

`services.event_cancellations.cancel` locks the event, then in one commit:

- closes intake that was ever opened with SCRUM-113's staged `close`,
- moves each live registration to Cancelled with SCRUM-134's staged `decide` write,
  which adds a history row, and leaves Withdrawn ones alone,
- locks the event's bookings and cancels each live one with
  `services.venue_bookings.stage_booking_cancellation`,
- releases the event's live equipment reservations by setting `released_at` and the new
  `released_by_id`, keeping each row and its quantity,
- moves the status, records who, when and why, and marks a pending request applied,
- stages the staff notifications through SCRUM-50's lifecycle module.

`stage_booking_cancellation` is SCRUM-109's own per-booking step, pulled out of
`stage_cancellation` without changing what that function does. SCRUM-109 still refuses a
Confirmed event for single-booking cancels, and its rule for which bookings are live is
the one used here.

Organiser requests live in `event_cancellation_requests`, one row per request, with a
partial unique index so only one is pending per event. Applied and declined rows stay.

Notifications go to the Organiser, the current Coordinator, and venue, technical and
safety staff recorded as acting on the event, keyed to the event since Cancelled happens
once. Attendee notifications are SCRUM-135, which waits on SCRUM-51.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Call SCRUM-109's `cancel_arrangement` per booking | It commits each booking on its own, so a later failure would leave some cancelled. |
| Copy the booking cancel into this service | The story forbids a second copy, and the two would drift. |
| Let `stage_cancellation` accept Confirmed events | That would let a single booking of a Confirmed event be cancelled, which SCRUM-109 refuses on purpose. |
| Keep the latest request in columns on the event | A second request would overwrite a declined one. |
| Delete or zero equipment reservations | The history of what was held would be lost (AC5). |

## Consequences

**Good**
- Everything the event held is released in the same commit as the status change, or
  nothing is.
- Each record type still changes in exactly one place.

**Bad / accepted trade-offs**
- The service touches four other stories' records, so a change to any of their staged
  operations should be checked against cancellation too.
- An expired hold the sweep has not marked yet is left for the sweep, as SCRUM-109 does.

**What this makes harder to change later**
- A new kind of event-owned commitment has to be added to `cancel`, or it will not be
  released.
