# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-09-08
- **Deciders:** Whole team
- **Related stories:** —

## Context

Five developers, all using AI assistants, working in parallel across ten epics over four sprints.
Two failure modes are near-certain without a written record: the same question gets re-decided
differently by different people, and by Week 13 nobody remembers *why* anything is the way it is.
The second is the expensive one — the module grades us on our ability to justify design decisions
and trade-offs in a live Q&A, and an unjustifiable design scores as "Unsatisfactory" no matter
how well the code runs.

Meeting notes are the wrong home for this: they are chronological, unsearchable, and not read
by anyone joining a piece of work later — human or machine.

## Decision

We will record significant decisions as ADRs in `docs/adr/`, using the lightweight template in
`0000-template.md`, merged in the same pull request as the code that implements them.
The ADR index is required reading before design work, for humans and AI assistants alike.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Capture decisions in Jira story comments | Buried per-story; cross-cutting decisions have no home; lost when we export the backlog |
| A single Confluence/Google "design decisions" doc | Becomes a dumping ground with no per-decision status; no review; drifts from the code |
| Nothing — rely on the C4 model | C4 shows *what* the structure is, never *why* we chose it or what we rejected |

## Consequences

**Good**
- Every design question in the Week 13 Q&A has a written, dated answer with rejected alternatives.
- New work — and every AI session — starts from the same constraints.
- Superseded ADRs are visible evidence of inspection and adaptation across sprints.

**Bad / accepted trade-offs**
- Roughly 15 minutes of writing per significant decision.
- Some judgement needed about what counts as significant; we will err towards writing one.

**What this makes harder to change later**
- Reversing a decision now costs a second ADR rather than a silent edit. This is intentional.
