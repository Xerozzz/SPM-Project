# ADR-0079: Use URL navigation and readable workspace presentation

- **Status:** Proposed
- **Date:** 2026-10-30
- **Deciders:** Sheryl (requested the six usability improvements), whole team at review
- **Related stories:** SCRUM-99 (inbox), SCRUM-28/29/46 (event forms and lists), SCRUM-40
  (bookings), SCRUM-59 (catalogue)
- **Extends:** ADR-0022, ADR-0071, ADR-0077, ADR-0078

## Context

Notifications show technical identities and their fragment links do not select hidden
workspace screens. Navigation state disappears on reload. Long dates, unfiltered lists
and permanently expanded creation forms make the workspace harder to use.

## Decision

Use `view` and `event` URL parameters with the browser History API. The role's existing
navigation list validates requested screens; event details open only after an identifier
appears in the user's permitted list. Backend authorisation remains unchanged.

Notification responses gain a nullable live event title, queried through recipient-scoped
notification records. No new database columns or stored presentation text are introduced.
The inbox renders readable type labels, retains source identities under Record details,
and shares its existing query cache with the sidebar's unread count.

Summaries use short Singapore dates while audit records retain full timestamps. Search
and venue/date filters apply only to records already returned by authorised APIs.
Creation and editing use separate form views. Dirty event and venue forms warn before
workspace navigation, browser navigation or closing/reloading the page discards changes.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Introduce a routing dependency | The History API covers this small workspace without a runtime dependency |
| Fetch every notification's event through its details endpoint | Adds per-row requests and some recipients cannot read full event details |
| Store event titles with each notification | Renames would leave stale titles and require a schema migration |
| Replace history timestamps with short dates | Makes precise action times harder to inspect |
| Search all events through a new endpoint | Existing permitted lists support the requested filters without widening access |
| Keep the venue form permanently expanded | Mixes browsing, creation and editing in one long screen |

## Consequences

**Good**
- Refresh, Back and notification links share the same workspace navigation state.
- Event titles remain private to notification recipients; IDs never grant access.
- Existing save, validation, booking and authorisation rules are retained.

**Bad / accepted trade-offs**
- Event titles are current values rather than historical snapshots.
- Search covers the loaded permitted list; server-side pagination would need matching filters.
- Native discard confirmations follow the browser's styling; no autosave is introduced.

**What this makes harder to change later**
- A future router must preserve the URL parameters and unsaved-change guards.
