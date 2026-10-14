# ADR-0031: Validate event venue requirements against the catalogue

- **Status:** Proposed
- **Date:** 2026-10-14
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-104

## Context

Organisers chose a venue requirement from a fixed list even though Venue Staff maintain the
current venue catalogue. This allowed choices that did not reflect the available venues.

## Decision

`event_requests.venue_requirement` remains a string, but it now stores an active venue name.
Organisers retrieve the alphabetically ordered names through an authenticated event-request
endpoint. The event-request service supplies the same active names to the pure domain validator
when creating, editing, or submitting a request.

## Consequences

- The organiser form and server share the active venue catalogue as their source of truth.
- Forged or stale selections receive the existing field-problem response.
- Deactivation removes a venue from new selections without changing existing requests.
- Selecting a venue remains a requirement only; it does not reserve it.
