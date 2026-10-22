# ADR-0049: Confirmation commits an event and its holds in one transaction

- **Status:** Proposed
- **Date:** 2026-10-22
- **Deciders:** Lee Yi Terng
- **Related stories:** SCRUM-80, SCRUM-79, SCRUM-110, SCRUM-83, SCRUM-108, SCRUM-34

## Context

`EventStatus.CONFIRMED` has existed since SCRUM-34, which needed the value so coordinator
assignment could ask "does this coordinator already have a confirmed event that day".
Nothing ever wrote it: `domain/event_status.py` said outright that the transition into it
"stays a later story's to add". SCRUM-110 made the same reservation on the booking side,
leaving `domain.venue_hold.confirm` as a function that only raised, with a note that
SCRUM-80 owned the real step.

So two things were waiting on this story at once: an event had no way to become
Confirmed, and a tentative hold had no way to become a real booking. Meanwhile the
customer's answer (Customer Clarification 3, which the workbook says takes precedence)
is specific about the order:

> The Event Coordinator marks the event Confirmed only after required venue and technical
> approvals **and the Safety Officer's operational safety approval** are complete. An
> event cannot proceed to preparation before safety approval.

Converting the holds at this moment is the team's reading of that, approved by the PO on
18 October 2026 and recorded on the ticket: approval places a time-limited hold
(SCRUM-83/SCRUM-110), and nothing else in the product ever turns one into a commitment.

## Decision

- **Confirmation is one transaction.** Under a row lock on the event, the prerequisites
  are rechecked, every live hold is converted to a confirmed booking, the status moves,
  and the audit is written. All of it commits or none of it does.
- **"Arranged" is SCRUM-79's rule, called rather than restated.**
  `domain.event_confirmation` asks `domain.safety_review.blockers` and reports its
  vocabulary. The two questions are genuinely the same question.
- **What confirmation adds is its own:** there must be a safety approval, it must be the
  latest decision, and its stored fingerprint must still match the plan (ADR-0048).
- **The prerequisites are rechecked at the moment of confirming**, never trusted from the
  readiness the screen was showing.
- **Venue Staff are not asked again.** Approval plus a live hold is sufficient; a
  confirmed booking already on the event is left untouched.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Move the status and let a sweep convert the holds afterwards | An event reading Confirmed while a hold is still Tentative — or has expired — is an event nobody can trust, and no sweep repairs a hold that ran out in between. |
| Restate the arrangement rules in the confirmation module | Two copies of "is this plan arranged" that nothing keeps in step. The first change to either would be a bug nobody sees until a Coordinator confirms something unsafe. |
| Trust the readiness the screen last read | A hold expires on a timer and an approval is spent by any plan change. Confirming on a stale answer is exactly what AC7 forbids. |
| Confirm automatically once the last prerequisite clears | The customer says the Coordinator marks it confirmed. It is also the only point where a human can notice something the rules cannot. |
| Ask Venue Staff to approve a second time at confirmation | They already decided; the hold is that decision. A second approval would make every confirmation wait on someone who has nothing new to say. |
| Let any Coordinator confirm | AC1 is explicit, and it matches SCRUM-104: an ordinary Coordinator acts only on the event assigned to them. |

## Consequences

**Good**
- The customer's ordering is enforced rather than documented: safety approval is a
  precondition no screen can skip.
- A confirmed event and its bookings cannot disagree, so nothing downstream has to cope
  with a half-confirmed event.
- `domain.venue_hold.confirm` is now the single route from Tentative to Confirmed, so any
  other way of confirming a booking fails loudly.

**Bad / accepted trade-offs**
- Any safety-relevant change to the plan spends the approval and blocks confirmation
  until the Officer looks again, including a change that makes the event safer.
- A confirmed event leaves the Coordinator's list, because that list holds Approved
  events. The confirmation is reported in the section's banner, but the event itself is
  no longer on the screen it was confirmed from.
- Nothing yet moves a Confirmed event back to planning in practice. The transition exists
  (SCRUM-47's `replan`), but the invalidation workflows that use it are SCRUM-47/SCRUM-81.

**What this makes harder to change later**
- Converting holds here ties the two commitments together. Splitting them later — say, to
  confirm an event whose venue is still being replaced — means deciding what a Confirmed
  event with an unconfirmed arrangement is, which is the question this avoids.

## Notes

The confirmation notification is SCRUM-50's, and the ticket says this story does not wait
for it. SCRUM-113 consumes confirmation status; AC11 is explicit that confirming does not
reopen suspended registration, so nothing here touches it.
