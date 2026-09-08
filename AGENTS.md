# AGENTS.md — Working agreement for humans and AI assistants

**This file is the single source of truth for how code is written in this repository.**
Every AI assistant (Claude Code, Cursor, Copilot, or otherwise) and every human contributor
must follow it. Tool-specific files (`CLAUDE.md`, `.cursor/rules/`, `.github/copilot-instructions.md`)
exist only to point here — do not put rules in them.

---

## 1. Project context

We are building **ConnectSphere**, an event-management system, for a university module (IS212)
that grades the **process** at least as heavily as the software. Two consequences that override
normal engineering instincts:

1. **Every contributor must be able to explain every line they submit**, unaided, in a live
   20-minute Q&A. Code you cannot explain is worth less than code you did not write.
2. **Traceability matters as much as correctness.** A feature with no story ID and no test
   scores badly even if it works perfectly.

If a suggestion is faster but less explainable, choose the explainable one.

## 2. Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (ORM), Alembic (migrations), Pydantic v2 |
| Database | PostgreSQL 16 |
| Frontend | React 18 + TypeScript, Vite, TanStack Query, Tailwind + shadcn/ui |
| Auth | JWT bearer tokens with role claims |
| Backend tests | pytest, pytest-cov, httpx ASGI client |
| Frontend tests | Vitest + React Testing Library |
| E2E | Playwright |
| Lint / format | ruff (Python), ESLint + Prettier (TS) |
| CI | GitHub Actions |
| Local run | Docker Compose (`api`, `web`, `db`) |

**Do not introduce a new runtime dependency without an ADR.** Dev-only tooling is fine.

## 3. Architecture rules

```
api/
  routers/      HTTP only: parse, authorise, delegate, serialise. No business logic.
  services/     Business logic and orchestration. Framework-agnostic where possible.
  domain/       Pure functions and value objects (suitability, overlap, state machine).
                No I/O, no ORM imports. This is where the interesting logic lives.
  repositories/ All database access. Services never import SQLAlchemy directly.
  models/       SQLAlchemy ORM models.
  schemas/      Pydantic request/response models.
  core/         Config, security, dependencies, notification dispatcher.
```

Hard rules:

- **A router function is at most ~15 lines.** If it is longer, logic has leaked out of a service.
- **`domain/` imports nothing from `api/` and nothing from SQLAlchemy.** This is what makes the
  hard logic (overlap detection, venue suitability, status transitions) unit-testable in
  milliseconds, and it is the strongest thing you can point at during the design Q&A.
- **Authorisation is never written inline.** Use the shared dependencies
  (`require_role(...)`, `require_event_access(...)`). If you find yourself writing
  `if user.role == ...` in a router, stop and extend the dependency instead.
- **The event status machine has exactly one implementation**, in `domain/event_status.py`.
  Nothing else may set `event.status` directly.
- **All datetimes are timezone-aware UTC** at every layer. Convert to local time only in the UI.
  Never store or compare naive datetimes.
- **Booking and equipment conflicts are prevented by the database**, via `tstzrange` +
  `EXCLUDE USING gist` constraints — not by an application-level "check then insert", which
  races. The application check exists only to give a friendly error before hitting the constraint.
  See `docs/adr/0002-booking-conflict-detection.md`.
- **No raw SQL built by string concatenation.** Parameterised queries or the ORM only.
- **Every schema change ships with an Alembic migration** in the same commit.

## 4. Testing rules

- **Every story ships with its tests in the same pull request.** There is no "we'll test it later"
  and no testing sprint. See `docs/DEFINITION_OF_DONE.md`.
- Mark every test with the story it proves:
  ```python
  @pytest.mark.story("US-14")
  def test_overlapping_booking_is_rejected(): ...
  ```
  This is how the traceability deliverable is generated — `pytest --collect-only` exports it.
- Test the **domain layer exhaustively** (pure, fast, cheap) and the API layer for the
  **happy path plus every authorisation and conflict failure**.
- Required for each core feature: at least one normal case, one boundary case, one
  authorisation-failure case, and — where relevant — one conflict case.
- Coverage gate is **90% on `api/`, 100% on `api/domain/`**. If a line genuinely cannot be
  covered, exclude it with a `# pragma: no cover` **and a comment saying why**. The module
  brief asks for coverage to be justified where it is not complete.
- Do not delete, skip, or `xfail` a failing test to make CI green. Fix the code or revert.

## 5. Decision records (ADRs)

Write an ADR **before** merging any change that:

- adds or removes a runtime dependency;
- changes the database schema in a way other code depends on;
- chooses between two viable technical approaches;
- introduces a cross-cutting pattern (auth, error handling, notifications, pagination);
- deliberately accepts a trade-off, limitation, or piece of technical debt.

Process: copy `docs/adr/0000-template.md`, number it sequentially, open it in the same PR as the
code, and link it from the PR description. ADRs are immutable once merged — to change a decision,
write a new ADR that supersedes the old one and mark the old one `Superseded by ADR-XXXX`.

**Before doing any design work, read `docs/adr/README.md`.** This applies to AI assistants too:
the ADR index is how the whole team — human and machine — stays consistent with decisions made
by someone else last week.

## 6. Rules specific to AI-assisted development

Everyone on this team uses AI. That is encouraged. These rules exist so it does not cost us marks.

1. **You own everything you submit.** Before opening a PR, read every line of the diff and
   satisfy yourself that you could defend it under questioning. If you cannot explain a line,
   delete it and write something you can.
2. **Small diffs.** Ask the assistant for one story's worth of change, not a feature area.
   A PR over ~400 lines of non-generated code will be sent back.
3. **Never let an assistant add a dependency, change CI, alter the auth dependencies, or edit
   a migration that has already been merged.** Those need a human decision and usually an ADR.
4. **Never accept a diff that disables a check** — deleted tests, `# noqa`, `# type: ignore`,
   `eslint-disable`, lowered coverage thresholds, `--no-verify`. If a check is genuinely wrong,
   change it deliberately in its own PR with a reason.
5. **Point the assistant at this file and at the relevant ADRs at the start of every session.**
   Consistency across five developers' assistants comes from shared written context, not from
   each person's prompting style.
6. **Disclose AI use in the PR template.** Not for shame — it is graded evidence of
   accountability, and it makes review focus on the right places.
7. **Regenerating is not debugging.** If output is wrong twice, work out why yourself.
   Understanding acquired at 2am is worth more in the Q&A than code that appeared by luck.

## 7. Conventions

- **Branches:** `feat/US-14-reject-overlapping-booking`, `fix/...`, `chore/...`, `docs/...`
- **Commits:** Conventional Commits, with the story ID: `feat(booking): reject overlapping venue bookings (US-14)`
- **PRs:** one story per PR, template completed, at least one approving review, CI green.
  No self-merging.
- **`main` is always releasable.** Branch protection is on; direct pushes are rejected.

## 8. Commands

```bash
docker compose up --build        # full stack at :5173 (web) and :8000 (api)
make test                        # backend tests + coverage gate
make lint                        # ruff + eslint
make fmt                         # ruff format + prettier
alembic revision --autogenerate -m "add booking exclusion constraint"
alembic upgrade head
npm --prefix web run test        # frontend unit tests
npx playwright test              # end-to-end
```

## 9. Things that will get a PR rejected

- Business logic in a router or a React component.
- `event.status = ...` outside the status machine.
- A naive datetime anywhere.
- An inline role check instead of the shared authorisation dependency.
- A new feature with no test, or a test with no story marker.
- A dependency added without an ADR.
- A diff you cannot explain.
