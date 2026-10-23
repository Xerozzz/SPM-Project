# ADR-0051: Record manual registration closure separately from suspension and deadlines

- **Status:** Proposed
- **Date:** 2026-10-23
- **Related stories:** SCRUM-113, SCRUM-42, SCRUM-86, SCRUM-115

## Context

Registration can already cease intake because its deadline passes or replanning suspends
it. Neither records the Organiser's distinct manual decision to close. Reusing either
would lose the reason a settings screen and later lifecycle workflow need to report.

## Decision

Store nullable `registration_closed_at` on the event request. Intake is closed whenever
this marker exists. Manual close is idempotent; it changes no planning fields, deadline,
suspension marker, or future attendee records. The reusable service operation has no
actor check, while the manual HTTP route uses the existing owner-only access dependency.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Set `registration_closes_at` to the current time | Loses the configured deadline and cannot distinguish a manual close from ordinary expiry. |
| Reuse `registration_suspended_at` | Conflates replanning's temporary safety guard with an Organiser's manual close. |

## Consequences

Completion and cancellation services can close intake without duplicating persistence
logic. A future explicit reopening operation must deliberately clear this marker.
