# ADR-0042: Confirmed events refuse ordinary updates

- **Status:** Proposed
- **Date:** 2026-10-20
- **Deciders:** Parikshit
- **Related stories:** SCRUM-36, SCRUM-37, SCRUM-47
- **Supersedes:** the status rule of ADR-0028

## Context

ADR-0028 let the assigned coordinator update the ordinary fields of an active request,
which reused the SCRUM-100 `ACTIVE_STATUSES` (Submitted, Approved or Confirmed).

SCRUM-36 was reopened after the Sprint 3 review. The customer clarified that the
information of a Confirmed event cannot be changed directly. Once an event is confirmed,
venue, equipment and registration have been arranged against it, so any change has to go
through the controlled significant-change process (SCRUM-37 to propose, SCRUM-47 to
decide).

## Decision

Ordinary updates are allowed only while a request is Submitted or Approved. The set is
`ORDINARY_UPDATE_STATUSES` in `api/domain/event_request.py`, read through
`accepts_ordinary_update()`. A Confirmed request is refused in three places:

- the shared dependency `EventAccess.UPDATE_PLANNING_INFO`, before the body is read
- the service, again on the locked row, so a request confirmed between the access check
  and the write is still refused
- the UI, which does not offer the editor for a Confirmed request
  (`acceptsOrdinaryUpdate` in `web/src/validation/planningInfo.ts`)

Everything else in ADR-0028 stands: only the assigned coordinator, only the ordinary
fields, through `PATCH /api/event-requests/{id}/planning-info`.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep allowing ordinary edits on Confirmed events | The customer ruled it out. Even a text change can affect what was arranged, such as layout or accessibility. |
| Remove Confirmed from `ACTIVE_STATUSES` | The Lead overview (SCRUM-100) still needs Confirmed events in that set. A separate set keeps the two rules apart. |
| Refuse only in the UI | The API would still accept the change from any other client. |

## Consequences

**Good**
- A Confirmed event can only change through a change request that the coordinator
  reviews against the current plan.

**Bad / accepted trade-offs**
- A typo in a Confirmed event's name now needs a change request, or waits until the event
  goes back to planning.

## Notes

This replaces the in-place note that PR #67 added to ADR-0028. ADR-0028 has been put
back to the text it was merged with, apart from its status line, as AGENTS.md asks.
