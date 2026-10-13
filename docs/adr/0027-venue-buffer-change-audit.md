# ADR-0027: Record a venue buffer change as an immutable snapshot, not a live relationship

- **Status:** Proposed
- **Date:** 2026-10-14
- **Deciders:** Lee Yi Terng
- **Related stories:** SCRUM-89 (identify bookings affected by a venue buffer change), SCRUM-81
  (recover from venue unavailability after booking)

## Context

SCRUM-89 asks for two things that look similar and behave oppositely.

Its AC3 and AC7 want a booking to be shown as needing action while it clashes, and for that to
stop on its own once it no longer does. ADR-0019 already settled how: the answer is derived from
the venue's current buffers whenever it is read, so there is no marker to clear. Nothing is
stored.

Its AC8 wants each buffer change recorded for audit, with the actor, the old and new values, the
time, and the bookings it made problematic. That must not change afterwards. An audit record whose
contents move when the world moves is not an audit record.

So one story needs a value that is always current and a value that is frozen, describing the same
event. The question this ADR settles is how to store the frozen half without it being mistaken for
a second, staler copy of the live half.

## Decision

**`venue_buffer_changes` stores one row per change, and `flagged_booking_ids` is an array of ids,
not a join table.**

The row holds both sides of the change rather than only the new values, so it stands on its own
without reading the row before it. `flagged_booking_ids` records what the actor was told at that
moment.

The array is the point. A join table with foreign keys would make the audit row's contents a live
relationship: delete or move a booking and the record of what someone was shown silently changes.
An array of ids says "these were the ids at the time" and keeps saying it. Reading it back answers
"what was this person told", which is the only question an audit record should answer. "What is
problematic now" is a different question, asked of the live review.

**The audit row is added to the session and committed by the caller**, not committed by the
service that builds it. `services.venue_buffer_review.record_change` only calls `db.add`; the
single commit is in `repositories.venues.save`. The venue change and the record of it therefore
land together, and a change that is rolled back leaves no record claiming it happened.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A join table with a foreign key to `venue_bookings` | Makes an audit record change when the thing it describes changes, which is the one property an audit record must not have |
| Store the derived marker on the booking and audit the transitions | Rejected by ADR-0019 for the live half; a stored marker also needs something to clear it, which is what the amended AC7 exists to avoid |
| Commit the audit row in `record_change` itself | Two commits for one logical change. A failure between them leaves either a venue change nobody recorded or a record of a change that did not happen |
| No audit at all, derive history from the bookings | There is nothing to derive it from. The buffers that were in force last Tuesday are not stored anywhere else |

## Consequences

**Good**
- The two halves cannot be confused: one table that never changes, and a question with no table
  behind it at all.
- A buffer change can never be refused by this, because nothing it writes can conflict. That is
  what lets SCRUM-89 AC5 hold.
- `old_*` and `new_*` on the same row means the history reads without joining it to itself.

**Bad / accepted trade-offs**
- `flagged_booking_ids` can name a booking that no longer exists. That is correct for an audit
  record and wrong-looking to anyone who reads it as a relationship, so any screen built on this
  table has to tolerate a missing booking.
- The table has no index on `changed_at`, which is how a history would be read. Added when
  something reads it; nothing does yet.
- `record_change` is only safe because its single caller commits immediately afterwards. A second
  caller that did not would have its audit row swept into an unrelated later commit. The
  docstring says so; the type system does not enforce it.

**What this makes harder to change later**
- Reporting across buffer changes (how often does this venue get re-timed, which bookings keep
  being caught) means unnesting an array rather than joining a table. Fine at this size, and the
  wrong trade if that reporting ever becomes a feature rather than an audit.
