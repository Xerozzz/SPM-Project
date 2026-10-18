# ADR-0035: Scope coordinator event access to the current assignment

- **Status:** Proposed
- **Date:** 2026-10-18
- **Deciders:** SCRUM-104 author, whole team at review
- **Related stories:** SCRUM-104
- **Supersedes:** ADR-0010 (read-only access for unassigned and other coordinators)

## Context

ADR-0010 let every coordinator read every submitted request, with write actions pinned to
the assignee. SCRUM-104 narrows that: a coordinator's list holds only events currently
assigned to them, and opening an unassigned event or another coordinator's event is
refused without disclosure — including its clarification history. Reassignment transfers
access immediately, while Leads keep full allocation visibility through their own routes.

## Decision

We will scope `GET /event-requests/reviewable` to the authenticated coordinator's ID and
narrow the shared `require_event_access(VIEW)` rule so an ordinary coordinator sees only
the event whose `coordinator_id` matches their own, with the Lead check first so dual
Lead+Coordinator accounts keep allocation visibility.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Hide buttons in the UI but keep the API readable | Anyone with a token could still read other events; the story demands refusal without disclosure |
| A separate "assigned-only" endpoint beside the old list | Two lists would drift apart; the old broad list is exactly what the story removes |

## Consequences

**Good**
- An unassigned or reassigned-away event disappears from the coordinator's list at once.
- The frontend renders no read-only card states; every listed event is actionable.

**Bad / accepted trade-offs**
- Coordinators can no longer browse colleagues' events for reference; Leads own that view.

**What this makes harder to change later**
- Any future cross-coordinator reference view needs its own permission, not a widening of VIEW.

## Notes

- ADR-0010 stays in the index marked `Superseded by ADR-0035` for the access rule only;
  its clarification-history storage decision is unchanged.
