# Architecture Decision Records

An ADR captures one significant decision: the context, what we chose, what we rejected, and
what it costs us. They are short — half a page is normal.

**Read this index before starting design or implementation work.** This applies to AI
assistants too: it is how five developers and five assistants stay consistent with decisions
someone else made two weeks ago.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-booking-conflict-detection.md) | Prevent booking conflicts with Postgres exclusion constraints | Accepted |
| [0003](0003-layered-architecture.md) | Layered architecture with an I/O-free domain core | Accepted |
| [0004](0004-ai-assisted-development.md) | How we use AI assistants and stay accountable | Accepted |
| [0005](0005-jwt-auth-for-sign-in.md) | JWT bearer auth with role claims for sign-in | Proposed — hashing superseded by ADR-0007 |
| [0006](0006-event-request-status-machine.md) | Event request storage, and status as a transition table in the domain layer | Proposed |
| [0007](0007-bcrypt-directly-not-passlib.md) | Hash passwords with bcrypt directly, not through passlib | Proposed |
| [0008](0008-coordinator-round-robin-assignment.md) | Derive round-robin coordinator assignment from assignment history | Superseded by ADR-0019 |
| [0009](0009-organisation-scoped-drafts.md) | Derive draft visibility from organiser organisation membership | Proposed — visibility rule superseded by ADR-0039 |
| [0010](0010-event-clarification-history.md) | Retain event clarification as a message history | Proposed — access rule superseded by ADR-0035, two-sided rule superseded by ADR-0036 |
| [0011](0011-event-request-review-decisions.md) | Store the current event-request review decision on the request | Proposed |
| [0012](0012-venue-soft-deactivation.md) | Deactivate venues instead of deleting them | Proposed |
| [0013](0013-venue-unavailability-before-booking.md) | Record venue unavailability before booking allocation exists | Proposed |
| [0014](0014-venue-bookings-search-scaffolding.md) | Keep a search-only venue_bookings table until booking allocation lands | Superseded by ADR-0015 |
| [0015](0015-venue-booking-requests.md) | Adopt venue_bookings for pending venue requests | Superseded by ADR-0026 (per-event pending-request restriction) |
| [0016](0016-application-booking-conflict-check-before-constraint.md) | Ship the application booking-conflict check before the exclusion constraint | Superseded by ADR-0017 |
| [0017](0017-venue-booking-approval-concurrency.md) | Enforce booking approval with the exclusion constraint and a booking-row lock | Proposed |
| [0018](0018-venue-booking-decisions.md) | Store the Venue Staff decision on the venue booking row | Proposed |
| [0019](0019-venue-buffer-effective-intervals.md) | Store the effective occupied interval so the overlap constraint can see buffers | Proposed |
| [0020](0020-manual-coordinator-assignment-queue.md) | Assign event coordinators manually via a Coordinator Lead queue | Proposed |
| [0021](0021-coordinator-assignment-history.md) | Retain coordinator assignment history as an append-only audit trail | Proposed |
| [0022](0022-notification-inbox.md) | Store private notifications for the in-app inbox | Proposed |
| [0023](0023-equipment-catalogue-identity.md) | Identify equipment catalogue entries by type and location | Proposed |
| [0024](0024-catalogue-backed-equipment-requirements.md) | Validate event equipment requirements against the catalogue | Proposed |
| [0025](0025-equipment-soft-deactivation.md) | Deactivate equipment catalogue entries instead of deleting them | Proposed |
| [0026](0026-multiple-venue-booking-requests.md) | Allow independent venue booking requests for one event | Proposed |
| [0027](0027-venue-buffer-change-audit.md) | Record a venue buffer change as an immutable snapshot, not a live relationship | Proposed |
| [0028](0028-ordinary-event-updates-by-assigned-coordinator.md) | Ordinary event updates after submission belong to the assigned coordinator | Proposed |
| [0029](0029-tentative-venue-holds.md) | Place a tentative venue hold on a pending booking request | Proposed |
| [0030](0030-expire-tentative-holds-with-an-in-process-timer.md) | Expire tentative venue holds with an in-process minute timer | Proposed |
| [0031](0031-catalogue-backed-venue-requirements.md) | Validate event venue requirements against the catalogue | Proposed |
| [0032](0032-use-catalogue-equipment-type-names.md) | Use catalogue equipment type names in event requirements | Proposed |
| [0033](0033-equipment-requirements-as-records.md) | Make an event's equipment requirements records, with the organiser's choice as the first one | Proposed |
| [0034](0034-equipment-review-outside-the-change-history.md) | Keep equipment requirement reviews out of the change history | Proposed |
| [0035](0035-coordinator-assigned-event-access.md) | Scope coordinator event access to the current assignment | Proposed |
| [0036](0036-internal-clarification-notes.md) | Treat clarification comments as internal Coordinator notes | Proposed |
| [0037](0037-plan-from-maintained-equipment-requirements.md) | Plan from the maintained equipment requirements, not the organiser's string | Proposed |
| [0038](0038-equipment-reservations-by-type-with-row-locks.md) | Reserve equipment by type, serialised with catalogue row locks | Proposed |
| [0039](0039-peer-organisers-see-calendar-projection-only.md) | Limit peer Organisers to the organisation-calendar projection | Proposed |

## When to write one

Anything on this list, **before the PR merges**:

- adding or removing a runtime dependency;
- a schema change other code depends on;
- choosing between two viable technical approaches;
- a cross-cutting pattern (auth, error handling, notifications, pagination);
- deliberately accepting a trade-off, limitation, or piece of technical debt.

## Rules

1. Copy `0000-template.md`, take the next number, open it in the PR that implements the decision.
2. ADRs are **immutable once merged**. To change your mind, write a new ADR and mark the old one
   `Superseded by ADR-XXXX`. The superseded record stays in the repository — a visible change of
   mind with a reason is evidence of adaptation, which is exactly what the rubric rewards.
3. Keep them short. If it takes more than a page, the decision is probably two decisions.
4. Number them at merge time to avoid collisions; if two PRs race, the second renumbers.
