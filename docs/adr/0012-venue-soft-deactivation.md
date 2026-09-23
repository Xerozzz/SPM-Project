# ADR-0012: Deactivate venues instead of deleting them

- **Status:** Proposed
- **Date:** 2026-09-23
- **Deciders:** Yi Terng
- **Related stories:** SCRUM-59 (venue catalogue)

## Context

The customer said Venue Staff can "create, view, update, and delete venue information"
(Customer Clarification 1, rows 43, 47 and 108). Two later requirements pull against a real
delete:

- A deactivated venue must not be selectable when someone searches the catalogue or raises
  a new booking request (SCRUM-59 AC3).
- A deactivated venue referenced by an existing event or booking must still be readable
  when that historical record is viewed (SCRUM-59 AC4).

A row that has been deleted cannot satisfy the second requirement. Venues are also about to
be referenced by the booking epic, where a foreign key to a missing venue would either block
the delete or orphan the booking.

## Decision

We will not delete venue rows. `venues.is_active` carries the state instead: "delete" in the
UI and in the customer's wording is implemented as deactivation, and the endpoint is named
`POST /venues/{id}/deactivate` so the API says what it does.

The catalogue has two reads as a result. `GET /venues` returns active venues only and is what
anyone choosing a venue sees. `GET /venues/{id}` returns the venue whatever its state, so an
event or booking that already names it stays readable.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Delete the row | Breaks AC4 outright, and will either block on or orphan the booking rows that the next epic adds. |
| Delete the row and copy the venue's details onto each booking | Every booking carries a snapshot, so the catalogue stops being the single source of truth and the same venue is described differently on different bookings. |
| Keep an `archived_venues` table and move rows into it | Two tables holding the same shape, and every read of a historical booking has to know which one to look in. |
| A `deleted_at` timestamp rather than a boolean | Records when, which nothing in this story asks for. A boolean says exactly what the rule is; a timestamp can be added later if an audit story needs it. |

## Consequences

**Good**

- AC3 and AC4 are both satisfied by the same column, and each read says which it wants.
- The booking epic can use a plain foreign key to `venues.id` with no cascade rules to design.
- The record survives, so a venue deactivated by mistake is recoverable: the row is still
  there and still correct.

**Bad / accepted trade-offs**

- Venue names stay reserved after deactivation, because the unique constraint covers every
  row. Reusing the name of a retired venue means choosing another name. We accept this:
  two venues with one name is exactly the confusion the constraint prevents.
- Every query that lists venues has to decide whether it wants active ones. The repository
  offers `list_active` for the selectable catalogue and a `get` that does not filter at all,
  rather than one function with a flag, so the decision is visible at the call site.
- The table grows monotonically. At the scale of one organisation's venues this is not worth
  managing.

**What this makes harder to change later**

- If venues ever genuinely need deleting (a record created entirely in error, say), that is a
  separate operation with its own rules about what to do with referencing rows, and a new ADR.

## Notes

- AC3 says the venue "cannot be selected" when a user "searches or creates a new venue booking
  request". Booking does not exist yet (that epic is later), so this release implements the
  half that can exist: the selectable catalogue excludes deactivated venues. The booking story
  inherits `GET /venues` and gets the rule for free.
- Reactivating a deactivated venue is not built. No acceptance criterion asks for it, and
  the decision above is what makes it possible later: the row and its details are still
  there, so reactivation is a flag change rather than re-entering the venue.
- Operating hours are stored as `time`, not `datetime`. They are wall-clock facts about a
  room rather than instants, so AGENTS.md's timezone-aware-UTC rule does not apply to them.
  The reasoning is repeated in `domain/venue.py` where a reader meets it first.
