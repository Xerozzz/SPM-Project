# ADR-0047: Let the owning Organiser and the current Coordinator read assignment history

- **Status:** Proposed
- **Date:** 2026-10-20
- **Deciders:** Sheryl (approved the change to `require_event_access`, AGENTS.md §6.3), whole team at review
- **Related stories:** SCRUM-105, SCRUM-97
- **Extends:** ADR-0021 (assignment history storage), ADR-0035 (coordinator access follows the current assignment)

## Context

SCRUM-97 recorded every assignment and reassignment in the append-only
`event_coordinator_assignments` table (ADR-0021), and exposed it through
`GET /event-requests/{id}/assignment-history` behind a Coordinator Lead role guard.
SCRUM-105 lets two more people read that trail: the Organiser who owns the event, and the
Coordinator currently assigned to it. Everyone else — peer or unrelated Organisers,
unassigned Coordinators, Venue Staff, Tech Support and Attendees — must still be refused
without disclosure. Lead access must not change, and access must follow reassignment at
once, as ADR-0035 already does for the rest of a coordinator's event access.

The SCRUM-97 response carries only user IDs, which mean nothing to an Organiser, so the
story also asks for each entry to name the previous Coordinator, the new Coordinator and
the acting Lead. Users have an email but no display name.

## Decision

We will add an access mode, `EventAccess.READ_ASSIGNMENT_HISTORY`, to the shared
`require_event_access` dependency and use it on the history route in place of the role
guard. It allows a Coordinator Lead, the owning Organiser, or the Coordinator whose ID is
on the request's `coordinator_id`, in any status. The route keeps reading the SCRUM-97
records; there is no second history store.

We will also extend `AssignmentHistoryRead` with `previous_coordinator_email`,
`new_coordinator_email` and `acted_by_email`, read by LEFT JOINing `users` three times in
the history query. The IDs stay in the response, so the change is additive. An email is
null when its user row is missing, and the UI shows "Unknown user" in its place. No
migration is needed.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Guard the route with the existing `VIEW` mode | VIEW refuses a Lead on a draft, so Lead access would narrow; it would also tie the audit trail to whatever VIEW grants in future |
| Keep the role guard and add `if` checks for owner and assignee in the router | An inline role check, which AGENTS.md §3 forbids |
| A separate organiser-facing history endpoint or table | Duplicates SCRUM-97's records and display; two trails could disagree |
| Resolve emails in the browser from `/assignable-coordinators` | That list is Lead-only and holds only active Coordinators, so Organisers, past Coordinators and Leads would stay unnamed |
| INNER JOIN `users` | A missing user row would silently drop the whole history entry instead of showing "Unknown user" |
| Copy the email onto each history row when it is written | Needs a migration and duplicates user data; older rows would still have none |

## Consequences

**Good**
- Reassignment moves history access with everything else, because the rule reads
  `coordinator_id` on every request rather than remembering past assignees.
- Each qualifying role is checked on its own, so an account that is also the owner or a
  Lead keeps that access after losing an assignment.

**Bad / accepted trade-offs**
- The owning Organiser now sees the email addresses of the Coordinators and Leads who
  handled their event. That is the point of the story, but it is new disclosure.
- The history columns are foreign keys to `users.id`, and no flow deletes users, so
  "Unknown user" cannot occur today. It is a defensive fallback, tested at the schema and
  UI layers rather than by breaking a foreign key in the database.
- The Lead's existing history view shows emails too, since it uses the same component.
- A non-Lead asking for a nonexistent request now gets 404 instead of 403, because the
  shared dependency loads the request before checking the caller. Every other per-event
  route already behaves this way.

**What this makes harder to change later**
- Widening who may read the audit trail is now an edit to this one access mode; it must
  not be done by widening VIEW.
- If users gain a display name, it belongs beside these three email fields. The table
  and the repository function SCRUM-102 notifications read are unchanged; only the HTTP
  response grows.

## Notes

- In the Organiser's request list and the Coordinator's review card, the history sits
  behind a "View assignment history" toggle and is fetched only when opened.
