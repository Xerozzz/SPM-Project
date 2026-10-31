# ADR-0072: Separate attendee registration summaries and details

- **Status:** Proposed
- **Date:** 2026-10-30
- **Related stories:** SCRUM-42, SCRUM-128
- **Extends:** ADR-0071

## Context

The attendee registration view currently expands every registration form and status in one
vertical list. It becomes difficult to scan when several events are available or registrations
are in different states.

## Decision

We will show attendee events as compact cards grouped by a status filter. The initial filter is
All events. Open events without a registration appear under Available; submitted lifecycles use
their existing registration status (`pending`, `waitlisted`, `accepted`, `withdrawn`, or
`cancelled`). Selecting a card's View details action reveals the existing registration form or
withdrawal action for that event.

The API remains unchanged: the screen continues to read the attendee's registration for each
event and derives the visual grouping in the client.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep every form expanded | It makes status scanning and comparing events difficult. |
| Add a new aggregate registration API | It is unnecessary for this presentation-only change and would broaden the API contract. |

## Consequences

- Attendees can quickly filter registrations by their current state without losing existing
  registration and withdrawal rules.
- Opening an event takes one additional click, consistent with My Events.
