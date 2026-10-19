# ADR-0036: Treat clarification comments as internal Coordinator notes

- **Status:** Proposed
- **Date:** 2026-10-18
- **Deciders:** Alvin
- **Related stories:** SCRUM-106

## Context

SCRUM-30 built clarifications as a two-sided conversation: Coordinators asked and
Organisers answered. SCRUM-106 changes the product rule: clarification comments are
internal working notes for the currently assigned Coordinator only. The owning
Organiser must not see them, and access must follow reassignment without copying
rows. The storage decision in ADR-0010 (append-only `event_clarifications` history)
still holds; only its two-sided access and response rule needs replacing.

## Decision

We will gate clarification list, read, and create on the current assignment
(`event.coordinator_id == current user`) via a new `READ_CLARIFICATIONS` permission,
remove the Organiser response endpoint, and render the thread only in the
Coordinator review card as internal notes.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep the response endpoint but hide it in the UI | The Organiser could still call the API directly; the product rule would be UI-only, not enforced. |
| Copy clarification rows to the new assignee on reassign | Copies diverge and leak history; the assignment foreign key already transfers access with no data movement. |
| Pin note reads to SUBMITTED like clarification requests | Notes must stay readable after the decision for handover; the status pin would hide history exactly when it is needed. |

## Consequences

**Good**
- One enforceable boundary: the backend refuses Organisers, unassigned, and other Coordinators with no disclosure.
- Reassignment transfers access automatically through `coordinator_id`.
- Notes remain readable after approval/rejection for audit and handover.

**Bad / accepted trade-offs**
- `ClarificationKind.RESPONSE` stays in the enum for old SCRUM-30 rows but no endpoint writes it; history reads may show legacy responses.
- Organisers get no clarification visibility at all, so Coordinators must use another channel for follow-up questions.

**What this makes harder to change later**
- Reintroducing two-sided clarifications needs a new ADR and a new permission; the removed response route must not be revived ad hoc.

## Notes

- Supersedes the two-sided access/response rule of ADR-0010; ADR-0010 storage stays.
- Follows the assignment-scoping pattern of ADR-0035.
