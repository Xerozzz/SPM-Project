# CLAUDE.md

Read **[AGENTS.md](./AGENTS.md)** first and follow it in full. It is the single source of truth
for architecture, testing, ADRs and AI-assisted development rules in this repository.

Then read **[docs/adr/README.md](./docs/adr/README.md)** — the index of architecture decisions —
before doing any design or implementation work, so your suggestions stay consistent with
decisions the rest of the team has already made.

## Session checklist

- Confirm which story ID you are working on. One story per branch, one story per PR. Keep each PR SMALL and reviewable
- Check `docs/adr/README.md` for a decision covering the area you are about to touch.
- Write the test alongside the code, marked `@pytest.mark.story("US-XX")`.
- If your change matches an ADR trigger in AGENTS.md §5, draft the ADR in the same change.
- Keep the diff small enough that the author can read every line before opening the PR.

## Never do these without being explicitly asked by a human in this session

- Add or upgrade a runtime dependency.
- Edit `.github/workflows/`, `api/core/security.py`, or any migration already on `main`.
- Delete, skip or `xfail` a test; add `# noqa`, `# type: ignore` or `eslint-disable`;
  lower a coverage threshold.
- Reformat or refactor files unrelated to the current story.
