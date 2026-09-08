# Scrum playbook — ConnectSphere

Owner: the Scrum Master. This is the operating manual for our process: cadence, ceremony
agendas, estimation, and what evidence gets captured where. Review it at every retrospective;
changing it is an act of adaptation and should be recorded as such.

---

## 1. Cadence

Four two-week sprints, with Week 12 kept clear for assembly and submission. Do not plan work
into Week 12 — the final sprint must be *finished* by then, and you will need those days.

| Sprint | Weeks | Theme | Milestone |
|---|---|---|---|
| 1 | 4–5 | Walking skeleton: auth, event draft/submit, one venue read path | Deliberately rough; the point is to learn our velocity |
| 2 | 6–7 | Venue discovery, review and coordination | **Week 7: instructor process consultation** — bring real artefacts, not a polished story |
| 3 | 8–9 | Booking, conflict detection, equipment | The hard logic; conflict cases proven by tests |
| 4 | 10–11 | Change requests, notifications, registration, hardening | **Showcase sprint** — all ceremonies recorded |
| — | 12 | No new development | Assemble the zip, slide deck, final backlog export; submit early |

**Fixed weekly rhythm** (adjust the days to your timetable, then never move them):

| Event | When | Timebox |
|---|---|---|
| Sprint planning | Monday of week 1 | 2 hours |
| Daily standup | Every weekday | 15 minutes, standing |
| Backlog refinement | Wednesday, both weeks | 1 hour |
| Sprint review | Friday of week 2 | 1 hour |
| Sprint retrospective | Friday of week 2, straight after review | 1 hour |

On standups: run a written async standup in the team channel every weekday, plus at least
three synchronous ones. Every attendance gap is visible, which is the honest signal you want.
Raise this at the Week 7 consultation and confirm your instructor is comfortable with it —
the brief asks you to consult before varying from the taught process.

## 2. Ceremony agendas

### Sprint planning (2 hours)

1. **PO presents the sprint goal** — one sentence describing a *workflow*, not a list of epics.
   Good: "An organiser can take an event from draft through coordinator review to a confirmed
   venue booking." Bad: "Finish the venue epic."
2. **Capacity check.** Each person states hours available this sprint, out loud. Subtract
   deadlines from other modules. Write the number down; you will compare it to actuals at the retro.
3. **Select stories** against last sprint's velocity — not against optimism. Stop selecting
   when you reach the number, even if it feels low.
4. **Decompose into tasks** of half a day or less. A task nobody can describe in a sentence
   is not understood well enough to start.
5. **Confirm the Definition of Done** applies to every selected story, with no exceptions.
6. **Sanity-check dependencies** — does anything here need an ADR before coding starts?

Output: sprint backlog in Jira, sprint goal written at the top of the board, capacity recorded.

### Daily standup (15 minutes)

Three questions, per person, addressed to the team and not to you. As Scrum Master you are
not collecting status — you are listening for impediments and for anyone who has been stuck
for more than a day. Take blockers offline; the standup identifies them, it does not solve them.

Watch for the AI-specific failure mode: "I've been going back and forth with the assistant on
this all day." That is a blocker, and it needs a human pair, not another prompt.

### Backlog refinement (1 hour, twice per sprint)

This is where you support the PO most. Agenda in §5 below.

### Sprint review (1 hour)

Demonstrate **working software** against the sprint goal, from a clean `docker compose up`,
run by someone who did not write the feature. Walk a complete workflow rather than clicking
through features. Capture what was not finished and why, honestly — that record is worth marks.

### Retrospective (1 hour)

Vary the format so it does not go stale: Sprint 1 *Start / Stop / Continue*, Sprint 2
*Mad / Sad / Glad*, Sprint 3 *Sailboat*, Sprint 4 *4Ls*. Every retro ends with **at most three
actions, each with a named owner and a due date**, and every retro *opens* by reviewing the
previous retro's actions. Un-actioned retros are the single most common way teams lose marks on
the "inspection and adaptation" descriptor — the improvement must be visible in the next sprint.

Standing agenda items for every retro:
- Are `AGENTS.md` and the Definition of Done still accurate? (see §4)
- Did our estimates match reality? Where were we systematically wrong?
- Any decision made this sprint that should have been an ADR and was not?

## 3. Estimation

- **Story points, planning poker, modified Fibonacci** (1, 2, 3, 5, 8, 13). Anything estimated
  at 13 must be split before it enters a sprint.
- **Pick a reference story in Sprint 1** — something small and well understood, call it a 2 —
  and estimate everything relative to it, all term. Consistency matters far more than accuracy.
- **Estimate effort and uncertainty, not hours.** "Venue search" and "booking conflict detection"
  might be the same hours and very different points, because one of them might not work.
- **Everyone estimates, including the person who will not build it.** Divergent estimates are the
  signal that the story is not understood — that conversation is the actual value of the exercise.
- **Record velocity every sprint** and plan the next sprint against the average of the last two,
  never against the best. Expect Sprint 1's velocity to be misleading; say so out loud rather
  than pretending otherwise.
- **Do not re-estimate completed stories** to make a burndown look better. Ever.

Track in Jira, but also keep a simple sheet: sprint, points committed, points completed,
capacity in hours, velocity. It makes the Week 7 conversation and the deck trivially easy.

## 4. Keeping five AI assistants in sync

This is a real coordination problem and it belongs to you. Three mechanisms:

1. **One rules file.** `AGENTS.md` is the source of truth; `CLAUDE.md`, `.cursor/rules/` and
   `.github/copilot-instructions.md` only point at it. Never let a rule live in a tool-specific
   file — it will drift and mislead.
2. **ADRs as shared memory.** Assistants read `docs/adr/README.md` before design work, so a
   decision one person made in Week 6 reaches everyone else's assistant in Week 9.
3. **A five-minute context sync at each planning session.** Ask the team: what did your assistant
   get wrong repeatedly this sprint? Whatever comes up is usually a missing line in `AGENTS.md`.
   Add it there and then. This turns individual friction into a shared asset, and it makes
   `AGENTS.md` visible evidence of adaptation rather than a file written once and forgotten.

Also worth saying plainly to the team once, early: **the person who accepted the diff owns it in
the Q&A.** Not the reviewer, not the assistant. That single sentence changes review behaviour
more than any checklist.

## 5. Supporting the Product Owner

The PO owns *what* and *why*; you own *how the process runs*. Do not write their stories for them
— but do make it easy for them to write good ones. Concretely:

- **Run refinement, don't attend it.** Timebox it, keep it on the top of the backlog only, and
  stop the meeting when it turns into design.
- **Guard the sprint.** New requests from the customer clarification process go to the PO and
  into the backlog, never into a running sprint. If something genuinely must come in, something
  else must come out, and the PO decides which — record that trade in the sprint notes; it is
  excellent evidence of responding to change.
- **Protect them from the team.** Developers will lobby for the technically interesting story.
  The PO's ordering stands.
- **Make readiness objective** using the checklist in `PO_TOOLKIT.md`, so "not ready" is a
  property of the story rather than an opinion about the PO.
- **Prepare their questions for the customer clarification process.** Ambiguity found during
  refinement should leave the room as a written question, not as an assumption. Log assumptions
  explicitly when a clarification will not arrive in time — the log itself is graded evidence.

## 6. Evidence capture — what to save, when, and where

Create `evidence/sprint-N/` at the start of every sprint and fill it as you go. Reconstructing
this in Week 12 is both painful and obvious to a marker.

| Moment | Artefact | Goes to | Feeds deliverable |
|---|---|---|---|
| Planning | Sprint backlog export, sprint goal, capacity note | `evidence/sprint-N/planning/` | 4 |
| Planning | Estimation record (poker results, points, divergences) | `evidence/sprint-N/planning/` | 4 |
| Daily | Written standup log | `evidence/sprint-N/standups.md` | 4 |
| Refinement | Refined stories with acceptance criteria | Jira | 1 |
| Mid-sprint | Task board screenshot, start and end of sprint | `evidence/sprint-N/board/` | 4 |
| End of sprint | Burndown chart | `evidence/sprint-N/burndown.png` | 4 |
| Review | Notes: what was demoed, feedback, what was not done and why | `evidence/sprint-N/review.md` | 4 |
| Retro | Board photo/export, actions with owners and dates | `evidence/sprint-N/retro/` | 4 |
| Continuously | ADRs | `docs/adr/` | 2, and the Q&A |
| Continuously | C4 diagrams as source (Structurizr DSL or Mermaid) | `docs/architecture/` | 2 |
| Every CI run | Traceability matrix | generated by `scripts/traceability.py` | 3 |
| **Sprint 4 only** | Recordings: planning, review, retro, one standup | unlisted video links in `evidence/sprint-4/recordings.md` | 4 |

**Sprint 4 recordings.** Record with the meeting tool's transcript on, upload as unlisted, and put
the links in a file — the brief explicitly says not to include the video files in the zip. Test
one short recording and one link in Week 9, so you are not discovering an upload limit at 23:00
on the Friday of Week 12.

## 7. Week 7 consultation — how to use it

It is ungraded, so use it for the things you are genuinely unsure about. Bring: your velocity
numbers so far, your burndown from Sprint 1 (however ugly), your Definition of Done, your retro
actions, and two or three real questions. A team that turns up saying "our first sprint
over-committed by 40% and here is what we changed" gets far more out of it — and reads far
better in Week 13 — than one presenting a tidy fiction.

## 8. Scrum Master anti-patterns to avoid

- Becoming the team's status reporter, or assigning work. The team pulls; you remove obstacles.
- Letting stories carry over silently. Carry-over is a planning signal — surface it at the retro.
- Running retros that produce feelings but no actions.
- Owning the backlog. That is the PO's job, and blurring it costs both of you marks.
- Doing the evidence collection alone in Week 11. Rotate the note-taker each sprint.
- Letting the "final sprint is the showcase" idea become "the first three sprints don't matter".
  Visible improvement *across* sprints is the thing being graded.
