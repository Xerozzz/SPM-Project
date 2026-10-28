# ADR-0068: Change request and completion entries, with a kind on each field change

- **Status:** Proposed
- **Date:** 2026-10-28
- **Deciders:** Sheryl (accepted the disclosure to Leads), whole team at review
- **Related stories:** SCRUM-120 (this PR: AC1 change requests, AC5 completion); SCRUM-37,
  SCRUM-47, SCRUM-86 write the records
- **Extends:** ADR-0064 (whitelisted field changes), ADR-0067 (lifecycle entries)

## Context

SCRUM-120 adds two more sources to the event history ADR-0062 builds from existing records.

- **Change requests (SCRUM-37/47):** `event_change_requests` keeps who asked, when and why,
  and the decision (who, when, note); `event_change_items` keeps each item's target, field,
  current and proposed value, as JSON. Nothing is overwritten, so old and new values are
  both retained. Dates are stored as ISO 8601 UTC text.
- **Completion (SCRUM-86):** `event_requests.completed_by_id` / `completed_at`, once, and
  every version of the closure record in `event_closure_notes` (ADR-0059). Completion writes
  version 1 in the same transaction; each correction adds the next version.

Two things did not fit the existing contract. ADR-0064's `changes` carry text, and the UI
shows it as is, but AGENTS.md §3 says datetimes are converted to local time only in the UI,
so a change to an event's start cannot be pre-formatted by the API. And change requests are
read elsewhere only by the owner and the assigned Coordinator (`READ_CHANGE_REQUESTS`),
while the history is also read by any Lead (ADR-0047, ADR-0062).

## Decision

We will add each field change's **`kind`**: `text` (the default, so every earlier reader is
unchanged) or `datetime`, meaning a UTC ISO 8601 instant that the UI shows in Singapore time.

We will add two readers under ADR-0064's rules:

1. **Change requested** (requester, time, reason, and every item as a field change) and
   **Change request decision** (decider, time, approved or rejected, note). The values are on
   the request entry only, so they appear once. The whitelist is `target.field` for the six
   event fields of SCRUM-37 AC2, a session's name, start and end, and an equipment line's
   quantity, technical requirements, addition and removal. An item outside it is never
   shown. Labels name what changed ("Session “Morning”: start", "Projector: quantity"); a
   whole line reads "Projector × 2 (HDMI)". The four start and end fields are `datetime`.
2. **Event completed**, carrying version 1 of the closure record (attendance and notes, with
   no old values), and **Closure record corrected** for each later version, with the
   previous version's values as old. Exactly those two fields, both sides, every time.

A return to planning caused by an approved change now links the decision entry through
`related_entry_ids` (ADR-0067).

We accept that **any Lead now sees change requests** in the history: the Organiser's reason,
the values asked for and the Coordinator's note. Per the Week 9 clarification, Leads have
access to all assigned and unassigned events, so this matches their role; it needs no
change to the access rules.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Format dates as text on the API | Breaks the UTC-everywhere rule and fixes the display timezone on the server |
| Let the UI detect ISO strings in any value | A free-text value that looks like a date would be reformatted; the reader knows, so it says |
| A separate typed field for each date (`old_start_at`, ...) | Rejected by ADR-0064 for the same reason: the schema grows with every source |
| Repeat the values on the decision entry | Shows them twice; the decision changes nothing about what was asked |
| Hide change requests from Leads | Needs a viewer rule in `core/dependencies.py`, and the Week 9 answer gives Leads this access |
| A separate entry for closure version 1 | It is written by the completion itself, in the same transaction: one action, one entry |

## Consequences

**Good**
- No migration, writer, route, access rule or ordering change. Earlier readers' changes are
  `text` by default.
- The original and corrected closure values are both visible, as ADR-0059 kept them to be.

**Bad / accepted trade-offs**
- **New disclosure to Leads:** change-request reasons, proposed values and decision notes.
- New actions are appended, so at one instant "Returned to planning" lists before the
  change decision that caused it; the return links the decision, so the cause stays one
  click away.
- A session or equipment line that cannot be found is labelled generically ("A session").
  Removed equipment lines keep their rows (SCRUM-43), so in practice this is rare.
- Each correction shows both fields whether or not each moved, as the buffer reader does.

**What this makes harder to change later**
- `kind` is part of the `changes` contract. A reader emitting a date must mark it, and its
  exact-field-set test pins which fields are dates.
