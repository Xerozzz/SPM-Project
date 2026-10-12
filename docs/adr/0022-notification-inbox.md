# ADR-0022: Store private notifications for the in-app inbox

- **Status:** Proposed
- **Date:** 2026-10-12
- **Deciders:** Whole team
- **Related stories:** SCRUM-99 (private inbox), SCRUM-96, SCRUM-102, SCRUM-95, SCRUM-94 (triggers)

## Context

SCRUM-99 needs a private in-app inbox with unread/viewed states; the next four
stories attach business triggers (submission, assignment, clarification, decision).
Each trigger must notify exactly the right recipients once, survive retries without
duplicates, and never leak one user's notifications to another. The inbox must show
the related event, the triggering action, and the occurrence time, newest first.

## Decision

We will store one row per recipient in a `notifications` table: recipient, event
request, finite type (`NotificationType` StrEnum, stable string values), source
identity (`source_type` + `source_id`), timezone-aware UTC `occurred_at` /
`created_at`, and nullable `viewed_at`. A unique constraint on
`(recipient_id, source_type, source_id)` makes retry idempotence a database
guarantee, not an application `if not exists` race. All recipient queries are
scoped by recipient ID and ordered by `occurred_at DESC, id DESC`. The API derives
the recipient from the signed token, never from browser input. Mark-viewed updates
only a row owned by the caller and is idempotent. Triggers stage their rows in the
same transaction as the business write, so both commit or roll back together.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| One row per event, fanned out at read time | Cannot record per-recipient viewed state; recipient-set changes would rewrite history |
| No stored rows, derive inbox from events/history tables | Every trigger needs its own query; viewed state has nowhere to live; ordering across trigger kinds is ad hoc |
| Event ID alone as dedup key | One event receives many clarifications and assignment changes; retries of one action would collide with distinct later actions |
| Presentation HTML stored in the row | Couples storage to UI copy; the inbox renders from type + event + time instead |

## Consequences

**Good**
- Exactly-once per recipient per source action, enforced by the database.
- Recipient isolation is structural: every query carries `recipient_id == caller`.
- Later stories reuse the same table, types, and staging pattern without new storage.

**Bad / accepted trade-offs**
- No polling or push in this story; the inbox refetches on mount and after mark-viewed.
- Requests with no trigger rows simply have no notifications; backfill is out of scope.

**What this makes harder to change later**
- `NotificationType` values are stored strings; renaming one needs a data migration.
- Source identity shape (`source_type` + `source_id`) is depended on by all four trigger stories.
