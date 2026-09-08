## Story

Closes **US-___** ( link to Jira issue )

Epic: ___

## What changed and why

<!-- Two or three sentences. Why this approach rather than the obvious alternative? -->

## Tests proving it

<!-- List the test names. Every story needs at least one negative test. -->

| Test | Scenario | Type |
|---|---|---|
| `test_...` | | unit / integration / e2e |
| `test_...` | authorisation failure | integration |

## AI assistance disclosure

> We are graded on accountability and explainability. Completing this honestly is a
> requirement, not a confession — it tells the reviewer where to look hardest.

- Tool(s) used: <!-- Claude Code / Cursor / Copilot / none -->
- Roughly what proportion of this diff originated from an assistant: <!-- e.g. ~70% -->
- Parts I directed most closely, or wrote by hand:
- Parts I reviewed most carefully because they were generated:
- [ ] **I have read every line of this diff and can explain and defend all of it without help.**

## Checklist

- [ ] All acceptance criteria met and demonstrable through the UI
- [ ] Layering respected; no logic in routers/components; no inline role checks
- [ ] All datetimes timezone-aware UTC
- [ ] Tests marked `@pytest.mark.story("US-XX")`; coverage gate passes
- [ ] Migration included if the schema changed, and it runs from empty
- [ ] ADR written if this hit an ADR trigger (AGENTS.md §5) — link: ___
- [ ] No checks disabled (no deleted tests, `# noqa`, `# type: ignore`, `eslint-disable`)
- [ ] Docs / `.env.example` updated if needed

## Reviewer

Reviewer: please confirm you could also explain this change in the Week 13 Q&A.
If you cannot, ask the author to explain it before approving — that conversation is the point.
