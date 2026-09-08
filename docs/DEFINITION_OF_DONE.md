# Definition of Done

Agreed by the whole team in Sprint 1 planning. Changes require a team decision at a retrospective,
recorded in the retro notes (this is graded evidence of inspection and adaptation — do not change
it informally).

## A story is Done when

**Functionality**
- [ ] Every acceptance criterion passes, demonstrated end-to-end through the UI, not just the API.
- [ ] The unhappy paths in the ACs behave correctly (unauthorised access, conflicts, invalid input).

**Code**
- [ ] Merged to `main` via a reviewed PR; branch deleted.
- [ ] Layering respected (AGENTS.md §3); no business logic in routers or components.
- [ ] Authorisation applied via the shared dependency, and it is covered by a test.
- [ ] Any schema change has an Alembic migration that runs cleanly from empty.
- [ ] No new lint, type or formatting errors.

**Tests**
- [ ] Unit tests for the domain logic; integration tests for the endpoint.
- [ ] Every test carries `@pytest.mark.story("US-XX")`.
- [ ] At least one negative test: authorisation failure, validation failure, or conflict.
- [ ] Coverage gate passes (90% overall, 100% on `api/domain/`).
- [ ] CI is green on `main` after merge.

**Traceability & explainability**
- [ ] The Jira story links to its PR, and the PR description lists the tests that prove it.
- [ ] The AI-usage section of the PR template is completed honestly.
- [ ] **The author can walk through the whole diff and explain why it is written that way.**
- [ ] If an ADR trigger was hit (AGENTS.md §5), the ADR is merged.

**Documentation**
- [ ] README still accurate if setup or run steps changed.
- [ ] New environment variables documented in `.env.example`.

## A sprint is Done when

- [ ] Every story in the sprint is Done by the definition above, or has been explicitly
      returned to the product backlog by the PO (never silently carried over).
- [ ] The increment runs from a clean clone with `docker compose up` — verified by someone
      who did not write the code.
- [ ] Burndown chart, task board and sprint backlog exported to `evidence/sprint-N/`.
- [ ] Review and retrospective held, notes committed, actions assigned owners and due dates.
- [ ] Velocity recorded and carried into the next planning session.

## Explicitly *not* part of Done

Stating these prevents scope creep and gives you a clean answer if an instructor probes:

- Production hardening (rate limiting, secrets management, horizontal scaling).
- Real email or SMS delivery — notifications are in-app, with an outbox table.
- Accessibility beyond capturing accessibility *requirements* as event/venue data.
- Features outside the 20 core requirements, however tempting.
