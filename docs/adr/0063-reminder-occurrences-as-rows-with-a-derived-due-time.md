# ADR-0063: A reminder occurrence is a row, and its due time is derived

- **Status:** Proposed
- **Date:** 2026-10-26
- **Deciders:** Lee Yi Terng
- **Related stories:** SCRUM-85, SCRUM-80, SCRUM-79, SCRUM-99, SCRUM-108

## Context

SCRUM-85 lets the assigned Coordinator ask to be told, some number of minutes before
their event, if anything is still outstanding. That is a scheduled job, and scheduled
jobs are where duplicate-send bugs live. The ticket is correspondingly strict:

- at most one reminder per event per configured occurrence, "even across worker retries
  or concurrent processing" (AC6);
- changing the schedule must not resend an occurrence already delivered (AC6);
- a change to the event's time recalculates future occurrences while "already-delivered
  history is retained" (AC8);
- a missed occurrence is processed once while the event is still upcoming, "without a
  burst of duplicate reminders" (AC7);
- and a failure "does not mark an undelivered reminder as sent" (AC8).

It is also explicit about where the answer comes from: "read the merged authoritative
state rather than introducing a second readiness calculation."

## Decision

- **An occurrence is a row.** `event_reminders` holds one row per lead time per event,
  carrying both the schedule and whether that occurrence has been processed. Identity is
  the row, not the moment.
- **The due time is derived, never stored**: the event's start less the lead time.
- **Processing locks the row** with `SELECT ... FOR UPDATE SKIP LOCKED`, and marks it
  processed in the same transaction as the notification it raised.
- **A row is marked processed whether or not a reminder was created.** Finding nothing
  outstanding is a result, not a reason to look again.
- **A kept lead time keeps its row** across a schedule change; only removed ones are
  deleted.
- **What counts as outstanding is `services.event_confirmations.readiness`**, called, not
  reimplemented.
- **A second minute timer** beside SCRUM-108's, not a second job inside it.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A separate deliveries ledger keyed on (event, due time) | Moving the event changes the due time, so a delivered occurrence would no longer match its own ledger entry and would send again — the opposite of AC8's retained history. |
| Store the due time on the row | Then AC8's "recalculate future occurrences" needs a migration of stored times on every event edit, and any edit path that forgot would leave reminders firing against a date the event no longer has. Deriving it means there is nothing to forget. |
| Rebuild the schedule from scratch on every edit | Simplest to write, and it forgets what has already been sent: AC6's "changing a schedule must not resend an occurrence already delivered" fails on the first edit. |
| Leave an occurrence unprocessed when nothing was outstanding | It would then be due forever, re-evaluated every tick, and would fire the moment anything slipped — hours or days after the moment the Coordinator actually asked about, and repeatedly. AC7 calls that a burst. |
| Advisory locks or a queue table instead of `SKIP LOCKED` | The row already exists and already needs locking. `SKIP LOCKED` is what SCRUM-108's hold sweep uses for the same problem, so the two read alike. |
| Recompute what is incomplete inside this story | Two definitions of "arranged" that nothing keeps in step. It is also how AC4's superseded-arrangement and action-required clauses would quietly diverge from SCRUM-80's. |
| One timer running both sweeps | A reminder run that threw would stop venue holds expiring. They share nothing but mechanics. |
| Snapshot the outstanding work into the notification | ADR-0022 keeps presentation out of the row, and a snapshot is a second copy of the readiness that goes stale the moment the Coordinator fixes something. The reminder names the event; what is outstanding is read live from it. |

## Consequences

**Good**
- AC6 is a flag on a locked row rather than a ledger to reconcile, and AC8 falls out of
  deriving the due time rather than being implemented.
- A missed tick loses nothing: the occurrence is still unprocessed and is picked up by a
  later run while the event is upcoming.
- AC4's harder clauses — superseded arrangements, action-required venues — are true
  without being written here, because they are SCRUM-80's rule.

**Bad / accepted trade-offs**
- Removing a lead time deletes its row and with it the record that its occurrence was
  sent. Adding the same lead time back re-arms it. That is two deliberate actions by the
  Coordinator, which we preferred to keeping rows nobody can see or remove.
- A reminder arrives up to one sweep interval after the moment asked for.
- The sweep's batch commits once, so every occurrence in a run lands together. Reading
  readiness is isolated per event so one unreadable event cannot starve the rest, but a
  failure in the commit itself still leaves the whole run for the next tick.
- About thirty lines of timer mechanics are duplicated from SCRUM-108.

**What this makes harder to change later**
- Running more than one API process means more than one sweep. `SKIP LOCKED` and the
  processed flag make that safe, but any future move to a real scheduler has to keep
  both, not replace them with an external queue's at-least-once delivery.

## Notes

AC5 asks the reminder to identify "the event and incomplete work". Under ADR-0022 the
notification carries no payload, so it identifies the event and says arrangements are
incomplete; which ones is read live from the event's own card, where the Coordinator has
to go to fix them anyway. Worth confirming with the PO, since it is the one place this
story reads the AC more loosely than its words.

AC6's "concurrent processing" rests on `SKIP LOCKED` and is argued rather than
demonstrated: the test suite's rolled-back session cannot run two real transactions, the
same limit `test_approve_venue_booking` already records.
