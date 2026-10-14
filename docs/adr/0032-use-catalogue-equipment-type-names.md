# ADR-0032: Use catalogue equipment type names in event requirements

- **Status:** Proposed
- **Date:** 2026-10-14
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-90

## Context

The equipment catalogue is the source of valid organiser choices, but local seed data and
fixtures used placeholder labels such as `Projector-type requirement`. They were not catalogue
types and made seeded data diverge from the organiser dropdown contract in ADR-0024.

## Decision

Event requirements and seed catalogue records use the real type names: `Projector`,
`Microphone`, `PA system`, and `Display screen`. Venue suitability maps these canonical type
names to the facility labels stored on venues.

## Consequences

- Seeded requests work with the same values the organiser can select.
- Existing local drafts using placeholder text must be updated before they can be submitted.
- A future free-form equipment type needs an explicit facility-mapping decision before it can
  participate in venue suitability matching.
