# Manual end-to-end testing

`docker compose up` seeds twelve test events, one for each stage of an event's life, so
every feature has something to try straight away. They are rebuilt every time the API
starts, so you can change or break them freely. To reset them, restart the API
(`docker compose restart api`) or run `make seed`. The three test venues are put back
too, including their setup and turnaround buffers.

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
| multi-role@example.com | Organiser and Coordinator | A second Organiser in the same organisation |

## The test events

| Event | State | What to test, and as whom |
|---|---|---|
| Test 01: Rejected, edit and resubmit | Rejected, with a reason | Organiser reads the reason, edits and submits again |
| Test 02: Awaiting review | Submitted, assigned, one internal note | Coordinator approves or rejects and adds notes. Lead reassigns to coordinator2 and checks the history |
| Test 03: Venue request waiting | Planning, venue request Pending | Venue Staff approves it (places a hold) or rejects it. Tech Support reviews the Projector. Coordinator edits planning info and checks the venue calendar |
| Test 04: Ready for safety review | Planning, venue held, Projector reserved | Safety Officer approves, rejects or asks for changes. The officer already has a "review due" notification |
| Test 05: Ready to confirm | Planning, safety approved | Coordinator confirms it. Coordinator sets reminders |
| Test 06: Confirmed, registrations open | Confirmed, intake open with a closing deadline | Organiser reviews registrations (one each of Pending, Accepted, Waitlisted, Withdrawn) and extends or closes intake. attendee@ registers and withdraws. Coordinator decides the waiting change request. Reminders are set |
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

## Every story, and where to test it

Every Done story was checked against this data on 27 Oct 2026, through the same API the
screens use, from an empty database. All passed.

| Story | Account | What to do |
|---|---|---|
| 27 Sign in | any | Sign in, then try a wrong password |
| 28 Create a request | organiser | Create a complete event request |
| 29 Save and resume a draft | organiser | Save an incomplete draft, find it again, finish it |
| 46 Submit for review | organiser | Submit Orientation Day. Submit Hackathon (draft) to see the field errors |
| 35 Status and allowed actions | organiser | Test 01 shows Rejected and offers Edit |
| 31 Review and decide | coordinator, organiser | Approve or reject Test 02. Edit and resubmit Test 01 |
| 30, 106 Clarification notes | coordinator, organiser | Add a note on Test 02. organiser@ cannot see the notes |
| 101, 96 Unassigned queue | coordinator-lead | Alumni Dinner is waiting, and the Lead has a notification |
| 34, 98 Assign | coordinator-lead | Assign Alumni Dinner to coordinator@ |
| 97, 102 Reassign | coordinator-lead, coordinator2 | Reassign Test 02 to coordinator2@, who is notified |
| 104 Coordinator access | coordinator | After the reassignment, coordinator@ can no longer open Test 02 |
| 105 Assignment history | organiser | View Test 02's assignment history |
| 100 Active assignments | coordinator-lead | Overview lists every active test event |
| 94 Decision notifications | organiser | Inbox has the approval and rejection |
| 87 Organisation calendar | organiser | Every test event is listed |
| 112 Peer Organisers | multi-role | Sees the calendar entries but cannot open organiser@'s events |
| 36 Planning information | coordinator | Edit Test 03's description |
| 37, 50 Propose a change | organiser, coordinator | Propose a change on Test 03. The coordinator is notified |
| 47 Decide a change | coordinator | Approve Test 06's change. The event goes back to planning |
| 130 Safety approval cleared | coordinator | After that, Test 06's confirmation readiness asks for a new safety review |
| 131 Intake suspended | organiser | After that, Test 06's registration is suspended |
| 43, 90 Equipment requirements | coordinator | Add a Microphone to Test 03. Only catalogue types are accepted |
| 124 Tech told | tech-support | Inbox has "equipment review needed" |
| 44 Review equipment | tech-support | Review Test 03's Projector as available |
| 52 Check availability | tech-support | Availability for Test 03 |
| 53 Reserve equipment | tech-support | Reserve Test 03's Projector |
| 84, 93, 103 Equipment catalogue | tech-support | Add, edit and deactivate an item |
| 49 Venue Staff told | venue-staff | Inbox has Test 03's venue request |
| 71 Existing venue request | coordinator | Test 03 shows its Pending request |
| 75, 110 Approve a venue request | venue-staff | Approve Test 03's request. It becomes a Tentative hold |
| 83, 73, 74 Holds block, conflicts | coordinator, venue-staff | Create and approve a new event on Test 03's date, request Test Hall East at the same time. The conflict shows and approving it is refused |
| 40 Reject a venue request | venue-staff | Reject that conflicting request with a reason |
| 121 Update a hold's expiry | venue-staff | Change Test 04's hold expiry |
| 108 Hold expiry | venue-staff, coordinator | Set Test 04's expiry two minutes ahead and wait. It expires and the coordinator is told |
| 78, 111 Sessions | coordinator | Add two sessions to Careers Fair, each with its own label and time |
| 109 Cancel one arrangement | coordinator | Cancel one of those sessions. The other stays |
| 55 Venue search | coordinator | Search by date, capacity and layout |
| 56 Suitability | coordinator | Check Test Studio's suitability for Test 12 |
| 38 Request a venue | coordinator | Request Test Studio for Test 12 |
| 54, 76, 77 Venue calendar | coordinator | Calendar for the next five weeks, availability for a period, and one entry's details |
| 59 Venue catalogue | venue-staff | Add, edit and deactivate a venue. Old Sports Hall is already inactive |
| 82, 89 Buffers | venue-staff | Put a held booking 30 minutes after Test 04's at Test Hall West, then give the venue 60 minute buffers. The clash is listed |
| 62 Closures | venue-staff | Add, edit and delete a closure |
| 81 Closure over a hold | coordinator | Test 11 shows the closure, and the coordinator has a notification |
| 116, 133 Replacement venue | coordinator, venue-staff | Request a replacement for Test 11, approve it, adopt it. The original is cancelled |
| 132 Closure replans a Confirmed event | venue-staff | Close Test Hall West over Test 07. It goes back to planning |
| 79 Safety review | safety-officer | Review Test 04. The officer had a "review due" notification |
| 80 Confirm | coordinator | Confirm Test 05 |
| 85 Reminders | coordinator | Set reminders on Test 05 |
| 113 Open and extend intake | organiser | Open Test 05's registration. Extend Test 06's deadline |
| 42, 51 Register | attendee | Register for Test 06, and see the notification |
| 128 Withdraw and re-register | attendee, attendee4 | Withdraw and register again. attendee4@ was withdrawn and can register again |
| 114 Review registrations | organiser | Test 06's registrations, in submission order |
| 134 Registration decisions | organiser | Accept Eve Pending on Test 06 |
| 129 Close intake | organiser | Close Test 06's registration. A new registration is refused |
| 99 Inbox | any | Mark a notification as viewed |
| 86 Complete an event | coordinator | Complete Test 08. Correct Test 09's record and see both versions |
| 88 Event history | organiser | Test 09's history |
| 115 Cancel an event | coordinator, organiser | Apply Test 07's request. Ask to cancel Test 05 and decline it. See why Test 10 was cancelled |
| 135 Attendees told | attendee2 | Inbox has Test 10's cancellation |

107 was replaced by 110, so there is nothing separate to test.
