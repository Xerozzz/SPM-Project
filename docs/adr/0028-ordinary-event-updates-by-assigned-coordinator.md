# ADR-0028: Ordinary event updates after submission belong to the assigned coordinator

- **Status:** Proposed, status rule superseded by ADR-0042, field list superseded by ADR-0046
- **Date:** 2026-10-14
- **Deciders:** Parikshit
- **Related stories:** SCRUM-36, SCRUM-29, SCRUM-31, SCRUM-100

## Context

SCRUM-36 asks that authorised users can view and update ordinary event planning
information, while date/time, expected attendance, venue requirements and equipment
requirements cannot change through that flow. The Week 4 brief says the system should
tell apart information that "may be edited normally" from "important changes that may
affect arrangements already made", and the Week 1 briefing says organisers request
changes after submission and the Event Coordinator reviews them.

Before this story, only the organiser could edit, and only a draft or rejected request
(SCRUM-29, `is_editable`). Once a request was submitted nobody could correct even a typo
in its name. The Sprint 2 review walkthrough raised exactly this.

## Decision

We will let only the assigned coordinator update the ordinary fields (name, purpose,
description, accessibility, layout, registration) of an active request (Submitted,
Approved or Confirmed, the SCRUM-100 `ACTIVE_STATUSES`), through a separate
`PATCH /api/event-requests/{id}/planning-info` endpoint. Access is a new
`EventAccess.UPDATE_PLANNING_INFO` mode in the shared dependency. The body schema forbids
every other field, so a protected field is a 422 and nothing is saved.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Let the organiser keep editing after submission | The briefing has organisers request changes and coordinators review them. Direct organiser edits would change a request the coordinator is in the middle of reviewing or planning. |
| Reuse the draft `PATCH /{id}` with a role-dependent field list | One endpoint would answer to two roles with two different field sets and status rules, and the existing draft tests and SCRUM-29 access would have to change. A separate endpoint leaves SCRUM-29 untouched. |
| Accept protected fields but silently ignore them | A coordinator would think a date change was saved. A 422 says plainly that it was refused. |
| Check the coordinator inside the service only | AGENTS.md section 3 says authorisation goes through the shared dependency, not inline. The service still re-checks on the locked row, only to catch a reassignment or rejection that happens in between. |

## Consequences

**Good**
- A submitted or approved request can be corrected without reopening it, and the
  fields that affect arrangements stay locked.
- Draft editing (SCRUM-29) and its tests are unchanged.

**Bad / accepted trade-offs**
- No history of who changed which ordinary field and when. The briefing's change
  history is not in this story.
- The organiser is not notified of the coordinator's change. They see it the next time
  they open the request.

**What this makes harder to change later**
- Letting another role make ordinary updates means changing the new dependency mode, not
  the endpoint.

## Notes

The field list is `ORDINARY_FIELDS` in `api/domain/event_request.py`, mirrored in
`web/src/validation/planningInfo.ts`.
