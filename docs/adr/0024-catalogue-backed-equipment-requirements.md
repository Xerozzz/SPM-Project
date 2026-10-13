# ADR-0024: Validate event equipment requirements against the catalogue

- **Status:** Proposed
- **Date:** 2026-10-13
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-90

## Context

Event requests currently use a fixed equipment-requirement vocabulary, while Technical
Support Staff maintain the actual equipment catalogue. Organisers must be able to select
only types currently recorded in that catalogue, and the server must reject a forged or
stale selection.

## Decision

We will retain `event_requests.equipment_requirement` as a string and populate it with an
equipment type from the catalogue. The organiser form reads distinct types through an
authenticated event-request endpoint. The event-request service loads the same types before
creating, editing, or submitting a request and passes them into the pure domain validator.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep the fixed frontend and domain lists | New or renamed catalogue types could never be requested. |
| Trust the dropdown without server validation | A stale page or crafted request could submit an unknown type. |
| Store an equipment-entry ID on event requests | The story asks for a type, not a particular location-specific entry; this would add an unavailable allocation design. |

## Consequences

**Good**

- The UI and server derive their choices from one catalogue source.
- Multiple location entries with one type appear once because the repository returns distinct values.

**Bad / accepted trade-offs**

- Existing requirement strings that are not present in the catalogue must be updated before a draft can be submitted.

**What this makes harder to change later**

- Allocating a specific item or quantity needs a new data model and decision record.

## Notes

The catalogue currently has no deactivation field. A later deactivation story can filter this
same repository query to active entries without changing the event-request contract.
