# ADR-0023: Identify equipment catalogue entries by type and location

- **Status:** Proposed
- **Date:** 2026-10-10
- **Deciders:** ConnectSphere team
- **Related stories:** SCRUM-84

## Context

Technical Support Staff need to record equipment inventory. The story requires an equipment
type, total quantity, location and operational status, and says that the same equipment type
and location must not be entered twice. This information must survive application restarts and
be available in the catalogue immediately after it is created. The team has selected three
operational statuses: Operational, Damaged, and Under Maintenance.

## Decision

We will store equipment in a dedicated PostgreSQL table, with a composite unique constraint on
`equipment_type` and `location`. The application will validate data for clear user feedback;
the database constraint remains the final protection against concurrent duplicate requests. We
will enforce the three selected operational statuses with a database check constraint.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep the catalogue in application memory | Inventory would disappear on restart and cannot be shared across API workers. |
| Make equipment type globally unique | The same type can legitimately be held at different locations. |
| Check duplicates only in the service layer | Two requests could both pass a pre-insert check and create duplicates. |
| Leave operational status as unrestricted text | Status labels would become inconsistent in the catalogue. |

## Consequences

**Good**

- A catalogue row has a stable, enforced identity that matches the story.
- The table owns the non-negative quantity rule as a last line of defence.
- Every entry uses one of the three agreed operational-status labels.

**Bad / accepted trade-offs**

- Type and location spelling must match exactly after whitespace is trimmed; broader naming
  normalisation is not part of this story.

**What this makes harder to change later**

- Allowing multiple entries for the same type and location would require a schema migration.

## Notes

The implementation follows ADR-0003's router/service/repository layering.
