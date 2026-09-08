# Product Owner toolkit — ConnectSphere

For the PO, maintained with the Scrum Master. Templates, a readiness checklist, the
prioritisation approach, and worked examples of the two hardest stories to use as reference.

---

## 1. Story template

```
US-XX  <short title>

As a       <role: Event Organiser | Event Coordinator | Venue Staff |
            Technical Support Staff | Attendee>
I want     <capability>
So that    <benefit — the reason this is worth building>

Epic:      <epic>
Priority:  Must | Should | Could | Won't (this release)
Estimate:  <points, set by the team, never by the PO>

Acceptance criteria
  AC1  Given <context>, when <action>, then <observable outcome>
  AC2  ...
  AC-neg  Given <a user without permission>, when <action>, then <refusal>

Notes / assumptions
  - <anything assumed pending customer clarification, dated>

Open questions for the customer
  - <question, and the date it was submitted through the clarification process>
```

Three things make the difference between a "Fair" and an "Excellent" story here:

- **The "so that" is real.** If it restates the "I want", the story has no articulated user need.
- **At least one negative criterion.** Who must *not* be able to do this, and what happens when
  they try? The rubric asks for edge cases explicitly, and roles are the core of this system.
- **Criteria are observable.** "The system handles conflicts gracefully" is not testable.
  "Then the booking is rejected with a message naming the conflicting event" is.

## 2. The three Cs

A story is a **Card** (the placeholder above), a **Conversation** (refinement — where the real
requirement is discovered), and a **Confirmation** (the acceptance criteria and the tests that
prove them). Cards written alone at midnight and never discussed are the classic way to lose
marks on "stories demonstrate user needs and conversations". Capture in the story's notes what
the conversation changed — including where a customer clarification altered your understanding.

## 3. INVEST check

| | |
|---|---|
| **I**ndependent | Can it be built without waiting on another unstarted story? |
| **N**egotiable | Does it describe a need rather than a screen design? |
| **V**aluable | Can you name the role that is better off, and how? |
| **E**stimable | Does the team understand it well enough to size it? |
| **S**mall | One person, a few days at most. Estimated 13? Split it. |
| **T**estable | Could someone write the test from the criteria alone? |

**How to split when a story is too big** — by workflow step, by role, by happy path versus
conflict handling, by "one item" versus "many with filtering", or by deferring the rules
(create the booking first, enforce non-overlap in the next story). Splitting by layer
("build the API", "build the UI") is not splitting — neither half is demonstrable at review.

## 4. Definition of Ready

A story may enter sprint planning only when all of these hold. This exists so that "not ready"
is a property of the story, not a judgement about the PO.

- [ ] Written in the template above, with a genuine "so that"
- [ ] Acceptance criteria in Given/When/Then, including at least one negative case
- [ ] Roles that may and may not perform the action are explicit
- [ ] No open customer question that would change the criteria — or the assumption is written down
- [ ] Dependencies identified and either done or scheduled earlier in the same sprint
- [ ] Estimated by the team, and 8 points or fewer
- [ ] The team agrees they could demonstrate it at review

## 5. Prioritisation

Order the backlog by **dependency first, then customer value, then risk**. For this project,
risk should be weighted higher than instinct suggests: the conflict-detection work is the most
likely thing to go wrong, and finding that out in Week 10 is fatal.

MoSCoW across the ten epics, with suggested sprints:

| Priority | Epic | Sprint | Reasoning |
|---|---|---|---|
| Must | Access and Role Management | 1 | Everything else depends on roles; also the first thing an instructor probes |
| Must | Event Request and Lifecycle | 1–2 | The spine of every workflow |
| Must | Venue Catalogue and Discovery | 2 | Read-side; unblocks booking and can proceed in parallel |
| Must | Review and Coordination | 2 | Completes the first demonstrable end-to-end workflow |
| Must | Venue Booking and Conflict Management | 3 | Highest technical risk — do it while there is still time to recover |
| Must | Equipment Planning and Reservation | 3 | Same overlap logic as booking; cheap once that pattern exists |
| Must | Event Change Management | 4 | Depends on bookings existing to disturb |
| Must | Notifications | 3–4 | Infrastructure in 3, per-event criteria ride on their triggering stories |
| Must | Attendee Registration | 4 | Self-contained; good sprint filler and a safe parallel workstream |
| Ongoing | Technical Enablers | 1, then as needed | One-off setup only; per-story quality lives in the Definition of Done |

Two notes on ordering. First, all twenty features are "Must" — the customer named them as core —
so MoSCoW here is really about *sequence and depth*, not about what to cut; be honest about that
rather than inventing a fake "Could". Second, plan each sprint as a **workflow that can be
demonstrated end to end**, cutting across three or four epics, rather than as "finish epic X".
The brief is explicit that the features are not isolated, and a review that walks a whole
workflow reads far better than one that clicks through screens.

## 6. Worked example — the hardest story

```
US-14  Prevent double-booking of a venue

As an      Event Coordinator
I want     the system to refuse a venue booking that overlaps a confirmed booking
So that    two events are never scheduled into the same room at the same time

Epic:      Venue Booking and Conflict Management
Priority:  Must
Estimate:  8

Acceptance criteria
  AC1  Given a confirmed booking for Venue A from 14:00–16:00 on 3 Nov,
       when a coordinator requests Venue A from 15:00–17:00 on 3 Nov,
       then the request is rejected and the response names the conflicting event.
  AC2  Given the same confirmed booking,
       when a coordinator requests Venue A from 16:00–18:00 on 3 Nov,
       then the request succeeds — touching boundaries do not overlap.
  AC3  Given the same confirmed booking,
       when a coordinator requests Venue B for an overlapping period,
       then the request succeeds.
  AC4  Given a booking that was cancelled or rejected,
       when a coordinator requests that venue for the same period,
       then the request succeeds — only confirmed bookings block.
  AC5  Given two coordinators submitting overlapping requests simultaneously,
       then exactly one succeeds and the other is rejected with a conflict.
  AC-neg  Given a user who is not the assigned coordinator for the event,
       when they attempt the booking,
       then it is refused and no booking is created.

Notes
  - Half-open intervals: a booking is [start, end), so 16:00–18:00 does not clash
    with 14:00–16:00. Confirmed with the customer on <date>.
  - AC5 is why this is enforced by a database constraint rather than a lookup — see ADR-0002.
```

AC2, AC4 and AC5 are the ones that separate this from an ordinary story: a boundary case,
a state-dependent case, and a concurrency case. Every conflict-related story in this project
should have that shape.

## 7. Worked example — a change that ripples

```
US-19  Request a date change after submission

As an      Event Organiser
I want     to request a change to my event's date after it has been submitted
So that    I can respond to circumstances without cancelling and starting again

Epic:      Event Change Management
Priority:  Must
Estimate:  8

Acceptance criteria
  AC1  Given an approved event, when the organiser requests a new date,
       then a change request is created and the assigned coordinator is notified;
       the event's existing details remain in force until the request is processed.
  AC2  Given a pending change request, when the coordinator approves it and the venue is
       available for the new date, then the event and its venue booking both move,
       and the organiser is notified.
  AC3  Given a pending change request, when the coordinator approves it but the venue is
       NOT available for the new date, then the coordinator is shown the conflict and the
       existing booking is not silently lost.
  AC4  Given an approved change of date, when equipment was reserved for the old date,
       then those reservations are re-evaluated against the new date and any that can no
       longer be met are flagged to Technical Support Staff.
  AC-neg Given an event that has been completed or cancelled,
       when the organiser attempts a change request, then it is refused.
```

AC3 and AC4 are the ripple effect the brief calls out — changes to an event affecting bookings,
equipment and notifications. Most teams will implement the date change and stop. Handling the
consequences is what the "Excellent" descriptors for working software and for stories describe,
and it is the most likely thing an instructor will ask you to demonstrate live.

## 8. Assumption and clarification log

Keep this in the backlog document; it is graded evidence of managing ambiguity.

| Date | Question asked / assumption made | Route | Answer | Stories affected |
|---|---|---|---|---|
| | | clarification process / assumed | | |

Remember: clarifications differ by section, and customer questions must not be posted in public
channels. Only your section's answers apply to your team.
