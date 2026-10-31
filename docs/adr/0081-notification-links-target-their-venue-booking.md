# ADR-0081: Target a venue booking from its notification

- **Status:** Proposed
- **Date:** 2026-11-01
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-49, SCRUM-78, SCRUM-99, SCRUM-111
- **Extends:** ADR-0022, ADR-0079

## Context

An event can have several independent venue requests. Each venue-request notification
stores the booking row as its `source_id`, but its workspace link used only the shared
event ID. Opening either notification therefore selected the first booking for that event
instead of the booking that created the notification.

## Decision

Venue-request, venue-revision, and venue-cancellation notifications will use a `booking`
URL parameter containing their stored `source_id`. The booking-decisions screen opens that
exact permitted booking. Other notifications continue to use the existing `event` parameter.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep the event ID and select the first matching booking | Multiple sessions make the target ambiguous. |
| Add a booking ID column to notifications | The existing `source_id` already is the booking identity. |
| Fetch a booking after opening the event | Adds a request and leaves URL navigation ambiguous. |

## Consequences

**Good**
- Each venue notification opens its originating session.
- The existing notification schema and booking authorisation are unchanged.

**Bad / accepted trade-offs**
- Workspace navigation has one resource-specific URL parameter alongside `event`.

**What this makes harder to change later**
- A future router must preserve both `event` and `booking` targets.
