# ADR-0050: Store operational registration intake controls apart from event planning

- **Status:** Proposed
- **Date:** 2026-10-23
- **Related stories:** SCRUM-113, SCRUM-42, SCRUM-47, SCRUM-81, SCRUM-109

## Context

`registration_requirement` is a locked planning description, not a record of whether
attendee intake is currently open. Opening, extending and suspending intake must not edit
that field, and replanning must require an explicit later reopening.

## Decision

Store nullable `registration_opened_at`, `registration_closes_at` and
`registration_suspended_at` on the event request. Intake is derived at the backend from
these values, the current clock and `EventStatus.CONFIRMED`; a passed deadline closes it
without rewriting or deleting registrations. A suspension marker is only cleared by the
owner's explicit open operation, never by reconfirmation. Existing non-blank
`registration_requirement` is the event's established opt-in signal.

## Consequences

Registration outcomes remain untouched by operational changes. Future attendee and
replanning stories call the same service guard/suspension operation, rather than copying
deadline or non-Confirmed-state checks.
