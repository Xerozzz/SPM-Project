# ADR-0039: Limit peer Organisers to the organisation-calendar projection

- **Status:** Proposed
- **Date:** 2026-10-19
- **Deciders:** Sheryl (approved the change to `require_event_access`, AGENTS.md §6.3), whole team at review
- **Related stories:** SCRUM-112, SCRUM-87, SCRUM-29
- **Supersedes:** ADR-0009 (same-organisation visibility rule only)

## Context

ADR-0009 let an Organiser view every request and draft created by another Organiser in the
same client organisation, and SCRUM-87 built the organisation calendar on top of that VIEW
rule. SCRUM-112 withdraws the shared view: a peer may see only that an event exists, its
name, its start and end, and its status. Everything else — the full request, the drafts
list, clarification notes, assignment history, venue bookings and equipment records — must
be refused to a peer at the API, not just hidden in the UI. An account that also holds a
Coordinator or Coordinator Lead role must keep that role's access.

## Decision

We will make `require_event_access(VIEW)` owner-only for the Organiser role, by removing
the same-organisation branch, and scope `GET /event-requests/drafts` to the caller's own
drafts. Organisation membership is then used in exactly one place: the
`GET /event-requests/organisation-calendar` query, whose fixed five-field response
(`id`, `name`, `start_at`, `end_at`, `status`) is everything a peer may learn. Selecting a
peer calendar entry in the UI shows those fields and makes no request to that peer's
individual event endpoint. The Coordinator and Lead branches of the dependency are
unchanged, so a dual-role account keeps them.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep VIEW open to peers and trim the response schema for them | Two shapes from one endpoint, chosen per caller; any new field or sub-resource behind VIEW leaks by default |
| Add a `CALENDAR_VIEW` permission and a per-event calendar-detail endpoint | The list already carries every field a peer may see, so a second endpoint adds surface with no new information |
| Hide details in the UI but leave the API readable | Anyone with a token could still read the request; ADR-0035 rejected the same approach for coordinators |

## Consequences

**Good**
- Every route behind VIEW — current and future — is closed to peers without per-route work.
- The calendar's peer-visible data is defined by one schema, so it is easy to audit.

**Bad / accepted trade-offs**
- Organisers can no longer review a colleague's draft before submission; the
  "Organisation drafts" UI section is removed.
- An owner's calendar-entry navigation is defined separately in ADR-0080; it does not
  widen a peer's calendar projection or API access.

**What this makes harder to change later**
- A future "share with my organisation" feature needs its own permission, not a widening
  of VIEW.

## Notes

- ADR-0009's `organisations` table and the `EventRequest.organiser_id -> User.organisation_id`
  derivation still stand; the calendar query depends on them. Only its visibility rule is
  superseded.
