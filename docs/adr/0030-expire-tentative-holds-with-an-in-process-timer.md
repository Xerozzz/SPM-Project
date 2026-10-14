# ADR-0030: Expire tentative venue holds with an in-process minute timer

- **Status:** Proposed
- **Date:** 2026-10-14
- **Deciders:** Parikshit
- **Related stories:** SCRUM-108, SCRUM-107, SCRUM-83, SCRUM-99

## Context

Week 7 change 4 says a tentative hold must expire on its deadline, stop affecting
availability, keep its history, and the assigned Event Coordinator must be told before or
when it expires. ADR-0029 left expiry to SCRUM-108 and chose to do it by changing the
hold's status rather than comparing `expires_at` with the clock on every read, because
the ADR-0002 overlap constraint cannot read the clock.

Nothing in the app runs on a schedule yet. Every action so far happens because a user
made a request.

## Decision

We will add a status `expired` and a service, `services.venue_hold_expiry.expire_due_holds`,
that moves every tentative hold whose `expires_at` has been reached to `expired` and
stages an inbox notification (ADR-0022) for the event's current assigned Coordinator in
the same commit. It runs:

- every minute, from a daemon thread started and stopped with the app
  (`core/hold_expiry.py`, hooked into `main.py`'s lifespan), and
- at the start of placing a hold or approving a booking, so those writes never see a
  hold that has run out as blocking, and the overlap constraint agrees with them.

Due holds are read `FOR UPDATE SKIP LOCKED`, so two runs at once never expire the same
hold twice, and the notification is keyed on the booking (`venue_booking`, booking id),
so a Coordinator is told exactly once per hold. A partial index on tentative holds'
`expires_at` keeps the lookup small (migration 0022).

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| A scheduler library (APScheduler, Celery beat) | A new runtime dependency (and for Celery a broker) for one job that runs once a minute. AGENTS.md section 2 asks for an ADR per dependency, and a thread does the job. |
| Expire only when someone reads or writes bookings | Every read path (search, calendar, availability, the booking lists) would need the call, several of them other people's code, and a Coordinator would not be told until someone happened to look. |
| Treat a hold past `expires_at` as not blocking, on every read | The overlap constraint cannot read the clock, so the app and the database would disagree about a hold that has run out (ADR-0029). |
| A Postgres job (pg_cron) | Not available in the stock `postgres:16` image we run, and it would put business rules in SQL outside the domain layer. |
| Warn the Coordinator a day before expiry as well | The AC allows "before or when". One notification at expiry is enough for the story and keeps one notification per hold. A warning can be added as its own type later. |

## Consequences

**Good**
- Holds expire on their own while the app is running, with no new dependency.
- Placing a hold and approving never trip over a hold that has run out.
- Expiry is one function, called the same way by the timer and by the tests.

**Bad / accepted trade-offs**
- A hold can keep blocking search, the calendar and the availability check for up to a
  minute after its expiry, until the next tick.
- Only while the API is running. Holds that ran out while it was down are expired on the
  first tick after it starts.
- With several API processes each would run a timer. `SKIP LOCKED` and the unique
  notification key keep that safe, only wasteful.
- The inbox shows the notification type as stored (`venue_hold_expired`), because the
  SCRUM-99 inbox does not have display labels yet.

**What this makes harder to change later**
- Anything else that must happen on a schedule should reuse this timer or replace it with
  a proper scheduler, rather than start a second thread.

## Notes

- Rule: `domain/venue_hold.py` (`is_due`, `expire`).
- Query: `repositories/venue_availability.due_holds_for_update`.
- Timer: `core/hold_expiry.py`. Interval: `INTERVAL_SECONDS = 60`.
