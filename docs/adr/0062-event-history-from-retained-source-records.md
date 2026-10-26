# ADR-0062: Build an event's history from the records each story already keeps

- **Status:** Proposed
- **Date:** 2026-10-26
- **Deciders:** Sheryl (approved both changes to `core/dependencies.py`, AGENTS.md §6.3), whole team at review
- **Related stories:** SCRUM-88; SCRUM-119 and SCRUM-120 add sources to it
- **Extends:** ADR-0021 (assignment history), ADR-0047 (who reads it), ADR-0036 (internal notes)

## Context

SCRUM-88 asks for one chronological history of an event: creation, submission, the
Coordinator's decision, clarification notes, assignments, venue requests and Venue Staff
decisions, and tentative holds being created, confirmed and expiring. It must read
records that already exist, add no audit table, write nothing when opened, and show each
action once. Later stories will add more kinds of entry (SCRUM-119 venue and equipment
changes, SCRUM-120 change requests, safety, confirmation, completion, cancellation).

The records were written by separate stories for their own purposes, and some keep less
than a history would like:

- `event_requests.submitted_at` and `decided_by_id` / `decided_at` / `rejection_reason`
  hold only their latest values. Rejected → resubmitted → approved leaves the second
  submission and the approval; the first submission and the rejection reason are gone.
- A venue booking keeps no record of its own confirmation. Confirmation (SCRUM-80) moves
  it to `confirmed` and writes `confirmed_by_id` / `confirmed_at` on the *event*, and
  those columns are overwritten when a replanned event is confirmed again. Migration
  0031 added only those two columns; there is no per-confirmation row.
- A hold's expiry is done by the minute sweep (ADR-0030): no actor, and the time the
  sweep ran is not stored, only the `expires_at` the hold lapsed at.
- Since SCRUM-110, approving a venue request *is* placing its hold and writes only
  `held_by_id` / `held_at`, so "approved" and "hold created" are one action.
- Assignments made before SCRUM-97 have no history row (ADR-0021).

## Decision

We will build the history on every read from the source records. Each source has one
small pure reader in `domain/event_history.py` that maps its record to entries, and
`timeline` concatenates, filters and orders them: by time, then a fixed rank per action,
then the record id, so equal times always come out in the same order. `(action, record
id)` is unique, which is both the entry's id and the "exactly once" guarantee. A new
source is a new reader and one line in `timeline`.

Where a record lacks something, the entry says so or is not made; nothing is invented.
An expiry has a null actor (shown as the system) and is dated by `expires_at`. A
confirmed hold is dated and attributed by the event's `confirmed_by_id` /
`confirmed_at`, accepting that after a replan and re-confirmation a hold confirmed the
first time shows the later confirmation. A test pins that behaviour. Only the latest
submission and decision are shown.

`GET /event-requests/{id}/history` is guarded by a new access mode,
`EventAccess.READ_EVENT_HISTORY`, sharing `READ_ASSIGNMENT_HISTORY`'s rule (any Lead, the
owner, the current assignee, no status pin) through one `in (...)` branch. Clarification
note entries are included only when the SCRUM-106 rule allows the caller to read notes.
That rule is extracted from the `READ_CLARIFICATIONS` branch into
`may_read_clarifications(...)`, which both that branch and the history route call, so
the history cannot show more or fewer notes than `GET /clarifications`. Everyone else
gets no trace of a note: no entry, no text and no id.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A second, append-only `event_history` table written by every action | The story forbids it; every writer would need changing, and two trails could disagree. ADR-0021 already keeps the one trail that needed its own table |
| Read the notifications table | It is a per-recipient private inbox (ADR-0022): not every action notifies, rows are duplicated per recipient, and an expiry or confirmation notification is not the source record |
| Reuse `READ_ASSIGNMENT_HISTORY` as it is | Widening the assignment trail's audience would silently widen this history too; ADR-0047 made that mode the place to widen the assignment trail |
| Show note entries to the owner and Leads without their text | Discloses that internal notes exist, which ADR-0036 refuses ("no disclosure") |
| Repeat the SCRUM-106 rule in the domain for the history | Two copies of an authorisation rule, kept equal only by a test, and the router would have to parse role claims itself |
| Add `confirmed_by` / `confirmed_at` to `venue_bookings` now | A schema change and a writer change in a read-only story; earlier rows would still need the event's values |
| Reconstruct lost submissions, decisions or pre-SCRUM-97 assignments | The actor or time is unknowable; inventing them would falsify the record (as ADR-0021 also concluded) |

## Consequences

**Good**
- No migration and no writer is changed; opening the history is a set of SELECTs.
- SCRUM-119 and SCRUM-120 add readers without touching ordering, filtering or the route.
- Note visibility has one implementation, shared with the notes route.

**Bad / accepted trade-offs**
- **Deliberate new disclosure to the owner and Leads.** As AC1 and AC6 require, they now
  see venue requests and Venue Staff decisions: the Venue Staff member's email, the
  decision reason, and the requested venue and session. No other screen shows them these.
  The reason is entered in a field labelled "Reason for the Coordinator", so Venue Staff
  may not expect the Organiser to read it; a follow-up could relabel that field.
- The gaps listed in Context are shown as gaps: one submission and one decision, a
  confirmation time that re-confirmation overwrites, an expiry with no actor.
- A booking cancelled after it was confirmed shows no confirmation entry, because nothing
  records that it had been confirmed; cancellation entries themselves are SCRUM-119's.
- A draft always has its creation entry, so the API never returns an empty list today;
  the UI's empty state is defensive.

**What this makes harder to change later**
- The response is computed, so its order and ids are only as stable as the source
  columns; a future migration that rewrites one of them changes the history.
- Widening the history's audience is an edit to `READ_EVENT_HISTORY`; widening who reads
  notes is an edit to `may_read_clarifications` and changes both routes together.

## Notes

- Venue cancellation (SCRUM-109) and replacement adoption (SCRUM-133) are arrangement
  changes after the fact and belong to SCRUM-119's venue-change entries, not here.
- SCRUM-89 buffer snapshots and the equipment records exist and are SCRUM-119's.
