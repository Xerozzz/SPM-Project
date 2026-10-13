# ADR-0025: Deactivate equipment catalogue entries instead of deleting them

- **Status:** Proposed
- **Date:** 2026-10-13
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-103

## Context

An equipment catalogue entry may no longer be offered, while existing event requirements
and reservations must keep their stored equipment information and identifiers.

## Decision

Add `equipment.is_active`, defaulting to true. Deactivation sets it false through
`POST /equipment/{id}/deactivate`; no row is deleted. Active catalogue reads and the
distinct equipment-type query used by event requests filter to active entries. A type stays
selectable while at least one of its location-specific entries is active.

## Consequences

- Historical references remain valid because the equipment row and its identifier remain.
- New requests cannot select a type whose entries have all been deactivated.
- There is no reactivation endpoint; that would require a later story.
