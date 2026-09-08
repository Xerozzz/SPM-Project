# ADR-0004: How we use AI assistants and stay accountable

- **Status:** Accepted
- **Date:** 2026-09-08
- **Deciders:** Whole team
- **Related stories:** cross-cutting

## Context

The module explicitly encourages AI for code generation while making the team accountable for
everything submitted, and it grades us on whether we can justify our code, architecture and
AI contributions in a live Q&A. Every developer on this team will use an assistant, and we are
using more than one tool between us.

Two risks follow. First, **divergence**: five assistants, each prompted differently, produce five
incompatible interpretations of the same codebase. Second, **unowned code**: a diff is accepted
because it is plausible and the tests pass, and nobody can explain it eight weeks later when it
matters most.

## Decision

1. `AGENTS.md` at the repository root is the single source of truth for all assistants.
   Tool-specific files (`CLAUDE.md`, `.cursor/rules/`, `.github/copilot-instructions.md`)
   contain no rules of their own — they point at `AGENTS.md`.
2. Assistants must read the ADR index before design work, so decisions propagate between people.
3. Every PR discloses AI use and carries an explicit attestation that the author has read every
   line and can defend it.
4. Assistants may not add dependencies, edit CI, touch the auth dependencies, alter merged
   migrations, or disable any check. Those require a human decision, and usually an ADR.
5. Reviewers ask the author to explain any part of a diff they find surprising, **before**
   approving. The review conversation is the mechanism, not the checkbox.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| No AI policy; trust individual judgement | Divergence is not a judgement failure, it is a coordination failure; and the Q&A risk is collective, not individual |
| Ban AI for core logic | Contradicts the module's explicit encouragement, and we would lose real velocity for a problem better solved by review |
| Per-tool rule files maintained separately | Guaranteed to drift; a rule updated in one file and not the others is worse than no rule |
| Require a written explanation of every AI-generated function | Enormous overhead; the PR attestation plus a live reviewer question achieves the same end |

## Consequences

**Good**
- One place to change a rule; every assistant picks it up.
- The disclosure section trains the habit of reading diffs properly, and is itself graded
  evidence of accountability.
- Reviewers know where to concentrate.

**Bad / accepted trade-offs**
- Disclosure adds a minute per PR and depends on honesty; we treat it as a norm, not a control.
- `AGENTS.md` must be kept current — a stale rules file is actively misleading. Reviewing it is
  a standing agenda item at each retrospective.

**What this makes harder to change later**
- Nothing technical. Relaxing the policy later would cost us the evidence trail, so we will not.
