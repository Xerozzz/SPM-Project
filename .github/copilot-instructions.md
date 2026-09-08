Read `AGENTS.md` at the repository root and follow it in full — it is the single source of truth
for architecture, testing, ADRs and AI-assisted development rules. Read `docs/adr/README.md`
before any design work.

Summary of non-negotiables:
- Layering: routers (thin) -> services (business logic) -> repositories (all DB access).
  `domain/` holds pure, I/O-free logic and is tested exhaustively.
- Authorisation only via shared dependencies (`require_role`, `require_event_access`).
- Only the status machine may set `event.status`.
- Timezone-aware UTC datetimes everywhere.
- Conflicts are prevented by Postgres `EXCLUDE USING gist` constraints, not application checks.
- Every story ships with tests in the same PR, marked `@pytest.mark.story("US-XX")`.
- Never add dependencies, edit CI, or disable lint/type/coverage checks.
