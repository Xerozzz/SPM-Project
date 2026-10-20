# ADR-0046: Layout and accessibility changes need change control

- **Status:** Proposed
- **Date:** 2026-10-20
- **Deciders:** Parikshit
- **Related stories:** SCRUM-36, SCRUM-37, SCRUM-47, SCRUM-79
- **Supersedes:** the field list of ADR-0028

## Context

ADR-0028 let the assigned Coordinator change the layout and accessibility requirements
as ordinary edits after submission. SCRUM-36 was reopened with a further criterion: an
ordinary edit must not leave affected approvals stale after an impactful layout or
accessibility change.

Layout and accessibility are exactly what Venue Staff judge a venue against, and later
what the safety review (SCRUM-79) checks. Changing either after a venue is approved can
make that approval wrong. SCRUM-37 already treats layout and accessibility as
significant changes, and SCRUM-47 decides them against the current plan, flagging
arrangements for replanning.

## Decision

Layout and accessibility are removed from the ordinary fields (`ORDINARY_FIELDS` in
`api/domain/event_request.py`, mirrored in `web/src/validation/planningInfo.ts`). The
planning-info body forbids them, so sending either is a 422 and nothing is saved. They
change only through a change request: the Organiser proposes it (SCRUM-37) and the
assigned Coordinator decides it (SCRUM-47).

Ordinary edits keep name, purpose, description and registration requirement.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep them ordinary and invalidate affected approvals on each edit | Needs the safety approval from SCRUM-79, which is not merged, and duplicates what SCRUM-47 already does for change requests. |
| Keep them ordinary only while no venue is approved | Two rules for one field, and the Coordinator cannot tell from the screen which applies. |

## Consequences

**Good**
- One path for every change that can affect arrangements, with its history kept.

**Bad / accepted trade-offs**
- A small wording fix to layout or accessibility now needs a change request.
