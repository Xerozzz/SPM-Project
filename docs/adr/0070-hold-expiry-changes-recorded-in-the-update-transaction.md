# ADR-0070: Hold expiry changes recorded in the update's transaction

- **Status:** Proposed
- **Date:** 2026-10-29
- **Deciders:** Sheryl (chose a required actor and a NOT NULL column), whole team at review
- **Related stories:** SCRUM-136 (this PR); SCRUM-121 writes the expiry, SCRUM-119 AC2 left
  the gap
- **Extends:** ADR-0064 (closes its AC2 gap), ADR-0068 (typed field values)

## Context

SCRUM-121's `PATCH /venue-bookings/{id}/hold` overwrites `venue_bookings.expires_at` and
keeps nothing else. The route received the Venue Staff user and discarded it. So the old
expiry, who changed it and when were lost, and ADR-0064 recorded the missing history entry
as a gap. That PATCH is the only path that changes an existing expiry: placing a hold sets
the first one, and the SCRUM-108 sweep changes status, not `expires_at`.

## Decision

We will add **`venue_hold_expiry_changes`** (migration 0044): `booking_id` (FK, indexed),
`old_expires_at`, `new_expires_at`, `changed_by_id` (FK `users`) and `changed_at`, all
NOT NULL, with a CHECK that old and new differ. Rows are never changed after they are
written.

- **Same transaction:** `update_hold_expiry` stages the row after every existing check and
  before the existing single commit. A refused update raises before staging; a failed save
  rolls back the row with the expiry. The booking row stays the only `FOR UPDATE` lock,
  taken first, so the lock order with the sweep and cancellation is unchanged.
- **Required actor:** `changed_by_id` is a required parameter, and the route passes the
  Venue Staff member. Four existing direct calls in tests now pass a staff user; what they
  assert is unchanged.
- **Same expiry is not a change:** the writer skips the row and the CHECK enforces it. The
  response and the SCRUM-122 notification are unchanged.
- **Reader:** one entry per row, **Hold expiry changed**, appended after `venue_closed`,
  with the venue, session and one whitelisted field change, `expires_at` "Held until", of
  kind `datetime`.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Nullable actor with a default, so existing callers need no change | Every real change comes from Venue Staff; a NOT NULL column states that, and only tests lacked an actor |
| Record an update to the same expiry | Nothing changed, and a retried PATCH would add duplicate entries |
| Add old-expiry columns to `venue_bookings` | Keeps only the latest change; several changes to one hold must all be shown |
| Write the record after the commit | The two could disagree after a crash between them |

## Consequences

**Good**
- Every expiry change from now on is shown once, with old and new values, actor and time.
- The hold's own entry and every other reader, the route and access are unchanged.

**Bad / accepted trade-offs**
- **Not back-filled:** changes made before migration 0044 have no row and no entry. For them
  the hold entry's "Held until" still shows the latest expiry, as ADR-0064 described.
- New disclosure to the owner and Leads: the Venue Staff member's email, as ADR-0064
  accepted for buffer changes.
- Downgrading drops the table and every recorded change.
- Appended rank: a change at the same instant as the hold lists after it, which is the
  order it happened.

**What this makes harder to change later**
- Any new path that changes `expires_at` must record a row too, or its change is missing
  from the history.
