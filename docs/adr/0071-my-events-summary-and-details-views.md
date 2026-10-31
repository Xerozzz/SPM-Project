# ADR-0071: Separate My Events summaries, details and creation

- **Status:** Proposed
- **Date:** 2026-10-29
- **Deciders:** Sheryl (requested the My Events redesign), whole team at review
- **Related stories:** SCRUM-46 (My Events), SCRUM-29 (drafts), SCRUM-28 (creation)

## Context

Each event card contains management controls and history, while the creation form is
always below the list. Three-column cards become crowded when registration or change
workflows open. The existing status filter initially hides everything except drafts.

## Decision

We will show compact event summaries with status, schedule, venue preference and a
View details action. Details show the existing controls and history for one event.
A Create event button opens the existing form separately. Saving or submitting returns
to My Events with confirmation. All events is the initial filter; returning from details
preserves the chosen filter. API permissions and workflow rules remain authoritative.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Expand every workflow inside each card | Registration and history make narrow cards hard to scan |
| Add a modal for the full event | Long forms and histories need more space, especially on mobile |
| Introduce URL routing now | A wider navigation change than this single-screen improvement requires |

## Consequences

**Good**
- The list stays compact and details use the available width.
- Existing workflow components, API calls and authorisation are reused.
- Only the selected event mounts its management components.

**Bad / accepted trade-offs**
- Management takes an extra click; details cannot be bookmarked and reload returns to the list.
- Returning from the form without saving discards its local edits.

**What this makes harder to change later**
- Shareable details links will require integrating this local selection with navigation.
