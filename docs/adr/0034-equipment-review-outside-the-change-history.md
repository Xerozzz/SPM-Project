# ADR-0034: Keep equipment requirement reviews out of the change history

- **Status:** Proposed
- **Date:** 2026-10-18
- **Deciders:** Divyaanshu Das
- **Related stories:** SCRUM-44 (review equipment requirements)

## Context

SCRUM-44 lets Technical Support Staff move a requirement out of `pending_review` and into
one of the outcomes ADR-0033 reserved for it (`available`, `partially_available`,
`unavailable`). ADR-0033 also introduced `equipment_requirement_changes`, the audit trail
for SCRUM-43 AC8.

That table is shaped around what SCRUM-43 changes: its `action` allows only `added`,
`updated` and `removed`, and its old and new columns cover quantity and technical detail.
It has no column for a review status.

## Decision

**A review status change writes no row to `equipment_requirement_changes`.** The
requirement's review state is updated in place, and that is all.

Writing one there anyway would mean recording it as an `updated` row whose old and new
columns are all unchanged, because the only thing that changed has nowhere to go. The row
would say someone touched the requirement without saying what it moved from or to, which
is worse than no row: it looks like history and isn't.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Record a review as an `updated` change row | Loses the from and to of the review, and makes a real edit and a review indistinguishable |
| Add a `reviewed` action and old/new review columns to the table | Widens SCRUM-43's merged audit table and migration for a second purpose; a review history deserves its own decision and story |

## Consequences

**Good**
- The change history still means one thing: what was asked for, and how that changed.
- No migration, and nothing already merged changes shape.

**Bad / accepted trade-offs**
- **We cannot tell who reviewed a requirement or when**, beyond the requirement's
  `updated_at`, which any later edit also moves. A follow-up story would add a
  review-history record.
- **The review list has no date filter.** It shows every live requirement of every
  approved event, so approved events whose dates have already passed still appear. That
  is accepted for now rather than guessing at a cut-off nobody has asked for.
