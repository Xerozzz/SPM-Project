# ADR-0041: Record a significant change as a change request with one row per changed value

- **Status:** Proposed
- **Date:** 2026-10-20
- **Deciders:** Parikshit
- **Related stories:** SCRUM-37, SCRUM-47, SCRUM-50, SCRUM-36

## Context

After submission the Organiser no longer edits the event (ADR-0028, customer clarification
rows 70 and 73). A change to the date, attendance, venue, sessions or equipment, or to a
layout or accessibility need that affects arrangements, has to be proposed and then decided
by the assigned Coordinator (SCRUM-47). The Coordinator must see each current value next to
the proposed one, and SCRUM-47 must be able to tell when the event moved on after the
proposal was made. A proposal can touch several things at once (row 71). A double-clicked
or retried submit must not create two requests, and SCRUM-50 later notifies the Coordinator
from the committed request.

## Decision

We will store a proposal as an `event_change_requests` row (reason, requester, time, the
event's `updated_at` as its version, and a client-supplied `submission_key`) with one
`event_change_items` row per changed value: what it changes (event, session or equipment
line), which row, the field, the current value and the proposed value. Values are JSONB.
A unique (event, submission key) pair makes a retried submit return the first request.
Proposing writes nothing to the event, its venue requests or its equipment lines.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Store the whole proposal as one JSON document on the request | Simpler to write, but the Coordinator's comparison and SCRUM-47's staleness check both work per value. One row per value keeps "current next to proposed" explicit and lets SCRUM-47 check each item against today's value. |
| Copy the whole event into a "proposed version" row | Holds every field, including ones nobody asked to change, so the Coordinator has to diff it. It also cannot hold session and equipment rows without copying those tables too. |
| Typed columns per field instead of JSONB values | Dates, numbers, text and a whole equipment line all appear as values. Typed columns would mean one nullable column per type or one table per target; JSONB with the item saying which field it is stays one small table. |
| Detect retries by comparing the new proposal with the last one | Two genuine identical proposals would be merged. A key per submit action tells a retry from a new request exactly, and the unique constraint holds even when two copies race. |

## Consequences

**Good**
- The Coordinator sees exactly what changes and from what.
- SCRUM-47 can refuse a stale request by comparing each item's current value, and the
  event version, with the event as it is when deciding.
- A retried submit is harmless, including under a race.

**Bad / accepted trade-offs**
- JSONB values are not type-checked by the database. They are written only by the
  service, from values the domain rules have already checked.
- Equipment items name the line by id. A line removed and re-added later is a different
  line, which is correct for history but means SCRUM-47 must treat it as stale.

**What this makes harder to change later**
- Adding a new kind of target (for example registration settings) means a new `target`
  value and rules in `domain/event_change.py`, not a schema change.

## Notes

Rules: `api/domain/event_change.py`. Access: `EventAccess.PROPOSE_CHANGE` and
`EventAccess.READ_CHANGE_REQUESTS` in `core/dependencies.py`.
