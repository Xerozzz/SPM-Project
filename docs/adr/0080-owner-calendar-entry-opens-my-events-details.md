# ADR-0080: Open an owner's calendar entry in My Events details

- **Status:** Proposed
- **Date:** 2026-10-31
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-112, SCRUM-87, SCRUM-46

## Context

ADR-0039 deliberately limits peer Organisers to the organisation-calendar projection.
That restriction currently gives an event owner the same limited panel when they select
their own calendar event. The owner already has a fuller, action-capable details view in
My Events, but must navigate there separately.

## Decision

When an Organiser selects a calendar entry, the client will compare its ID with the
caller's existing own-event list. An owner is sent to the selected My Events details view;
a peer remains in the calendar projection. The client never requests a peer's individual
event endpoint to make this decision.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Add the organiser ID to the calendar response | It widens ADR-0039's deliberately fixed peer-visible projection. |
| Request `GET /event-requests/{id}` first and fall back on 403 | It creates a forbidden request for every peer click and treats authorisation as normal control flow. |
| Keep the owner in the calendar projection | It leaves owner controls inaccessible from a natural entry point. |

## Consequences

**Good**
- Owners reach the existing full details and permitted actions directly from the calendar.
- Peers continue to see only name, schedule, and status.

**Bad / accepted trade-offs**
- The first calendar selection may require loading the caller's own-event list.

**What this makes harder to change later**
- A dedicated owner indicator in the calendar response would require revisiting ADR-0039's
  fixed response shape.

## Notes

This changes only owner navigation; API authorisation remains unchanged.
