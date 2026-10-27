# Manual end-to-end testing

`docker compose up` seeds twelve test events, one for each stage of an event's life, so
every feature has something to try straight away. They are rebuilt every time the API
starts, so you can change or break them freely. To reset them, restart the API
(`docker compose restart api`) or run `make seed`.

The events are built in `scripts/seed_scenarios.py` through the same code the screens
use. They sit on their own venues (Test Hall East, Test Hall West, Test Studio) about
three weeks ahead, so they never clash with the automated E2E tests.

## Accounts

Every password is `password123`.

| Account | Role | Use it for |
|---|---|---|
| organiser@example.com | Organiser | Owns every test event |
| coordinator@example.com | Coordinator | Assigned to every test event |
| coordinator2@example.com | Coordinator | Reassignment target |
| coordinator-lead@example.com | Coordinator Lead | Unassigned queue, assignment, overview |
| venue-staff@example.com | Venue Staff | Venue requests, holds, closures, catalogue |
| tech-support@example.com | Tech Support | Equipment review and reservations |
| safety-officer@example.com | Safety Officer | Safety reviews |
| attendee@example.com | Attendee | Not registered anywhere, so can register |
| attendee2@ to attendee5@example.com | Attendee | Already registered on Test 06 |

## The test events

| Event | State | What to test, and as whom |
|---|---|---|
| Test 01: Rejected, edit and resubmit | Rejected, with a reason | Organiser reads the reason, edits and submits again |
| Test 02: Awaiting review | Submitted, assigned, one internal note | Coordinator approves or rejects and adds notes. Lead reassigns to coordinator2 and checks the history |
| Test 03: Venue request waiting | Planning, venue request Pending | Venue Staff approves it (places a hold) or rejects it. Tech Support reviews the Projector. Coordinator edits planning info and checks the venue calendar |
| Test 04: Ready for safety review | Planning, venue held, Projector reserved | Safety Officer approves, rejects or asks for changes. The officer already has a "review due" notification |
| Test 05: Ready to confirm | Planning, safety approved | Coordinator confirms it. Coordinator sets reminders |
| Test 06: Confirmed, registrations open | Confirmed, intake open | Organiser reviews registrations (one each of Pending, Accepted, Waitlisted, Withdrawn) and extends or closes intake. attendee@ registers and withdraws. Coordinator decides the waiting change request. Reminders are set |
| Test 07: Cancellation requested | Confirmed, Organiser asked to cancel | Coordinator applies or declines the request |
| Test 08: Ended, ready to complete | Confirmed, ended yesterday | Coordinator completes it with attendance and notes |
| Test 09: Completed | Completed with a closure record | Coordinator corrects the record. Organiser, Lead and staff read it. Event history shows every step |
| Test 10: Cancelled | Cancelled, everything released | Organiser sees when and why. attendee2@ has the cancellation notice |
| Test 11: Venue closed over a hold | Planning, held venue now closed | Coordinator sees the closure and requests a replacement venue. Venue Staff approve it. Coordinator adopts it, which cancels the original |
| Test 12: Venue rejected, find another | Planning, venue request rejected, a change approved | Coordinator searches for another venue and requests it. Organiser sees the approved change |

The original samples are still there: **Orientation Day** and **Hackathon (draft)** are
drafts (the Hackathon is incomplete, to show field errors), **Careers Fair** is in
planning with nothing arranged, and **Alumni Dinner** is waiting in the Lead's
unassigned queue.

## Features not tied to one event

- **Venue catalogue:** Venue Staff add, edit and deactivate venues. Old Sports Hall is
  already inactive.
- **Venue search and calendar:** Coordinator searches by date, capacity, layout and
  facilities. The test venues show holds, bookings and the Test Studio closure.
- **Closures:** Venue Staff add a closure over Test 06's booking at Test Hall East to see
  a Confirmed event return to planning, with registrations suspended.
- **Organisation calendar:** the Organiser sees every event in the organisation.
- **Lead overview:** the Lead sees every active event and who owns it.
- **Notifications:** every account has notifications from building the events above.
  Mark some as viewed.
