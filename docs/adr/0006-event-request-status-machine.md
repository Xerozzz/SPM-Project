# ADR-0006: Event request storage, and status as a transition table in the domain layer

- **Status:** Proposed
- **Date:** 2026-09-12
- **Deciders:** Yi Terng (author), whole team at review
- **Related stories:** SCRUM-46 (submit), SCRUM-30 (clarification), SCRUM-31 (review and decide), SCRUM-35 (view status and allowed actions)

## Context

Six stories in the first two sprints move an event request between statuses or ask which
actions are currently allowed. They are being built in parallel by different people. Without
one agreed place for "which moves are legal", each story will encode its own version of the
rule in a service or, worse, a router — and the Week 13 question "how do you know a request
cannot be submitted twice?" will have five answers.

AGENTS.md §3 already says the status machine has exactly one implementation in
`domain/event_status.py` and that nothing else may set `event.status` directly. This record
fixes *what shape* that implementation has, so every story adds to the same thing.

## Decision

We will represent the status machine as **data**: a closed `EventStatus` enum and a
`frozenset` of `(from, to)` pairs in `api/domain/event_status.py`. A single `transition()`
function checks the pair and returns the new status or raises `InvalidTransitionError`. Named
helpers (`submit()`, later `approve()`, `reject()` …) are one-line wrappers so call sites read
as intent. `is_editable()` / `ensure_editable()` answer the "may this still be changed
directly" question from the same module.

Services persist whatever the machine returns:

```python
request.status = event_status.submit(request.status)   # the only assignment, value from the machine
```

Statuses are stored as their lowercase value in a `VARCHAR(30)` column (SQLAlchemy `Enum` with
`native_enum=False`), so adding a status is a code change, not a Postgres type migration.

**The table itself** (`event_requests`, migration `0003`) is shared by every event request
story, so its shape is part of this decision:

- One row per request, owned by `organiser_id` (FK to `users`), with all eleven fields the
  ticket names (`name`, `purpose`, `description`, `start_at`, `end_at`,
  `expected_attendance`, and the venue / accessibility / equipment / layout / registration
  requirements), plus `created_at`, `updated_at`, `submitted_at`.
- **Every content column is nullable.** The ticket calls the fields "required", but they are
  required *to submit*, not *to exist*: SCRUM-29 saves half-finished drafts. Completeness is
  therefore a domain rule (`domain/event_request.py`, run at submission) rather than a
  `NOT NULL` constraint, and the rule can name every missing field at once.
- Datetimes are `timestamptz`; the API converts any offset to UTC on the way in (AGENTS §3).

Vocabulary so far: `draft`, `submitted`. Each story that introduces a status or a transition
adds it here, with tests, in the same PR — and no story invents a status elsewhere.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| `if status == ...` checks inside each service | Rules scatter across stories; nothing stops two services disagreeing; impossible to list all legal moves in the Q&A |
| Methods on the ORM model (`request.submit()`) | Couples the rule to persistence; cannot be unit-tested without the ORM, which ADR-0003 forbids in `domain/` |
| A state-machine library | A new runtime dependency (needs an ADR of its own) for what is a dozen lines we can all read |
| Postgres native `ENUM` type | Every new status becomes an `ALTER TYPE` migration; painful to test and to roll back |
| `NOT NULL` on the required fields | Makes partial drafts impossible, and a database constraint can only report the first missing field, not all of them |
| One table per status (draft table, submitted table, …) | Submission becomes a copy between tables; ids change; every reader has to union them |

## Consequences

**Good**
- The complete set of legal moves is one `frozenset` that a reviewer can read in seconds.
- Every transition is exercised by millisecond-fast unit tests with no database (ADR-0003).
- SCRUM-35 ("allowed actions") can derive its answer from the same table rather than
  re-stating the rules.

**Bad / accepted trade-offs**
- Transitions that depend on *data* (e.g. "may only approve if a venue is available") need a
  guard outside the table; the table only knows about statuses. Those guards live in services
  and call the machine last.
- Everyone touching the lifecycle edits the same small file — merge conflicts are likely but
  trivial (one line in a set).

**What this makes harder to change later**
- Little. The module has no dependencies, so moving to a richer model is a local change.

## Notes

- Implementation and tests: `api/domain/event_status.py`, `api/tests/unit/test_event_status.py`.
- Storage: `api/models/event_request.py`, migration `0003`.
