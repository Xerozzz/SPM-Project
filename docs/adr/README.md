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
| [0008](0008-coordinator-round-robin-assignment.md) | Derive round-robin coordinator assignment from assignment history | Accepted |
| [0009](0009-organisation-scoped-drafts.md) | Derive draft visibility from organiser organisation membership | Proposed |
| [0010](0010-event-clarification-history.md) | Retain event clarification as a message history | Proposed |

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
