# ADR-0061: Gate end-to-end tests behind a label with a nightly run

- **Status:** Proposed
- **Date:** 2026-10-25
- **Deciders:** alvinkoh
- **Related stories:** SCRUM-49

## Context

PR #366 was blocked by a billing failure, not a code failure. The repository runs the
full Playwright suite (Compose build plus Chromium) on every PR to `main`. The team is
on a limited free plan. Backend and frontend unit checks are cheap; the E2E job is the
costly one.

## Decision

We will keep backend and frontend jobs on every PR, and run the Playwright job only when
the PR carries an `e2e` label, plus on a nightly schedule and manual dispatch.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep E2E on every PR | Cost that blocked PR #366; unit gates already catch most regressions. |
| Remove E2E from CI entirely | Loses the only full-stack signal; nightly keeps it without per-PR cost. |
| Path-filter only (`e2e/**`, `web/**`, `api/**`) | Still fires on most PRs since most touch `api/` or `web/`. |

## Consequences

**Good**
- Per-PR minute cost falls to lint plus unit tests.
- Full-stack signal retained via nightly and opt-in label.

**Bad / accepted trade-offs**
- A PR without the label can merge with green unit tests but broken cross-service flow.
- Nightly failures are found later and need triage back to a PR.

**What this makes harder to change later**
- Re-enabling per-PR E2E is a second ADR superseding this one.

## Notes

- Target: [.github/workflows/ci.yml](../../.github/workflows/ci.yml), `e2e` job.
- Human must apply the workflow edit per AGENTS.md §6.3; assistant drafts ADR only.
- Suggested gating: `if: contains(github.event.pull_request.labels.*.name, 'e2e')`, plus `schedule` (nightly) and `workflow_dispatch`.
