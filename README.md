# ConnectSphere

Event-management system for IS212. This repository currently contains the **development
scaffold**: the infrastructure, tooling and conventions every feature story is built on.
No product features exist yet — that is deliberate.

Before writing any code, read **[AGENTS.md](./AGENTS.md)** (how we work) and
**[docs/adr/README.md](./docs/adr/README.md)** (decisions already taken). They apply to
humans and AI assistants alike.

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Docker Desktop | 24+, with Compose v2 | Runs the whole stack; nothing else is required |
| Git | any recent | — |

That is the whole list. Python, Node and PostgreSQL run **inside** the containers, so you
do not need them installed to run the application. (`make` is optional, and is not
available on Windows by default — every target below is also given as a plain
`docker compose` command.)

## Run the application

```bash
git clone <this-repo>
cd SPM-Project
cp .env.example .env
docker compose up --build
```

The first build takes a few minutes. When it settles:

| URL | What you should see |
|---|---|
| http://localhost:5173 | The web app, showing "API and database are ok" |
| http://localhost:8000/health | `{"status":"ok"}` |
| http://localhost:8000/docs | Interactive OpenAPI documentation |
| `localhost:5432` | PostgreSQL — user, password and database are all `connectsphere`. Set `POSTGRES_PORT` in `.env` if 5432 is taken |

If the page shows the health status, all three containers are talking to each other and
the database migrations have run. That is the entire point of the scaffold.

Stop it with `Ctrl+C`, then:

```bash
docker compose down
```

Add `-v` to delete the database volume as well and start completely fresh:

```bash
docker compose down -v
```

## Everyday commands

Each row gives the `make` target and the command it runs, so you can use either.

| Task | make | Plain command |
|---|---|---|
| Start the stack | `make up` | `docker compose up --build` |
| Stop it | `make down` | `docker compose down` |
| Backend tests + coverage gate | `make test` | `docker compose run --rm api pytest --cov=. --cov-report=term-missing --cov-fail-under=90` |
| Frontend tests | `make test` | `docker compose run --rm --no-deps web sh -c "npm run test -- --run"` |
| Backend lint + types | `make lint` | `docker compose run --rm api sh -c "ruff check . && ruff format --check . && mypy ."` |
| Frontend lint + types | `make lint` | `docker compose run --rm --no-deps web sh -c "npm run lint && npm run typecheck"` |
| Autoformat the backend | `make fmt` | `docker compose run --rm api sh -c "ruff format . && ruff check --fix ."` |
| Autoformat the frontend | `make fmt` | `docker compose run --rm --no-deps web npm run fmt` |
| Apply migrations | `make migrate` | `docker compose run --rm api alembic upgrade head` |
| New migration | `make revision m="add users table"` | `docker compose run --rm api alembic revision --autogenerate -m "add users table"` |

`make test`, `make lint` and `make fmt` each run both of their rows. Every one of these
runs inside a container, which is why Docker is the only prerequisite — you do not need
Python or Node on your machine. `make down ARGS=-v` wipes the database volume too.

The API container runs `alembic upgrade head` and then the dev seed on every start, so a
normal `docker compose up` has the schema up to date and accounts you can sign in with.
Backend tests always run against a separate `<database>_test` database — `api/tests/conftest.py`
rewrites `DATABASE_URL` on the way in, and `api/tests/integration/conftest.py` creates and
migrates it — so tests never touch what you see in the browser, whatever credentials you
configured.

### Seeded accounts

All passwords are `password123`. `make seed` re-runs the seed by hand; users are never
modified once created, but the sample event requests are reset to Draft each time.

| Email | Roles | Sample data |
|---|---|---|
| `organiser@example.com` | organiser | Two event requests: "Orientation Day" (complete) and "Hackathon (draft)" (incomplete) |
| `coordinator@example.com` | coordinator | |
| `venue-staff@example.com` | venue_staff | |
| `tech-support@example.com` | tech_support | |
| `attendee@example.com` | attendee | |
| `multi-role@example.com` | organiser, coordinator | |

### End-to-end tests

Playwright runs on your machine against the running stack, so it is the one thing that
needs Node installed locally:

```bash
docker compose up -d --build
cd e2e
npm ci
npx playwright install --with-deps chromium
npx playwright test
```

## Configuration

All configuration comes from environment variables.
**[.env.example](./.env.example) documents every one of them** — copy it to `.env` and
edit. `.env` is gitignored and must never be committed; if you add a variable, add it to
`.env.example` in the same pull request.

`docker-compose.yml` repeats the same defaults, so the stack also starts from a clean
clone with no `.env` at all. That is how CI brings it up.

`JWT_SECRET` deliberately has no default in the code: the API refuses to start without
one, so nobody can accidentally ship a well-known signing key.

## Repository layout

```
.
├── AGENTS.md                   How we work — single source of truth for humans and AI
├── docker-compose.yml          web + api + db, one command
├── .env.example                Every environment variable, documented
├── Makefile                    Thin wrapper over the docker compose commands
├── api/                        FastAPI backend
│   ├── main.py                 App factory, CORS, /health
│   ├── core/                   Config, database session, security, dependencies
│   ├── domain/                 Pure logic — no I/O, no ORM, no framework (ADR-0003)
│   ├── models/                 SQLAlchemy ORM models
│   ├── schemas/                Pydantic request/response contracts
│   ├── repositories/           The only layer that queries the database
│   ├── services/               Business orchestration
│   ├── routers/                HTTP only — parse, authorise, delegate, serialise
│   ├── alembic/versions/       Migrations, numbered by hand
│   └── tests/                  unit/ and integration/, each test tagged with its story
├── web/                        React 18 + TypeScript + Vite + Tailwind
│   └── src/api/client.ts       The one place the frontend calls the API
├── e2e/                        Playwright, against http://localhost:5173
├── docs/adr/                   Architecture decision records — read the index first
└── scripts/traceability.py     Generates the story-to-test matrix from pytest markers
```

The layering (`routers -> services -> repositories -> database`, plus a pure `domain/`)
is [ADR-0003](./docs/adr/0003-layered-architecture.md), and ruff enforces it: importing
SQLAlchemy or FastAPI inside `domain/` fails the lint step.

## How the pieces connect

- The browser only ever talks to `localhost:5173`. The Vite dev server proxies `/api` and
  `/health` through to FastAPI (see `web/vite.config.ts`), so there is no CORS in
  day-to-day development and no API base URL to configure per environment.
- The API reaches PostgreSQL over the Compose network at `db:5432`, and waits for the
  database's healthcheck before it starts.
- `api/` and `web/` are bind-mounted into their containers and run with hot reload, so a
  saved file is live within a second or two, with no rebuild.

## Writing a story

1. Branch: `feat/SCRUM-14-short-description`. One story per branch, one story per PR.
2. Check [docs/adr/README.md](./docs/adr/README.md) for a decision covering what you are
   about to touch, and write an ADR if you hit a trigger in AGENTS.md section 5.
3. Write the code in the right layer, and the test beside it, tagged with the story:

   ```python
   @pytest.mark.story("SCRUM-14")
   def test_overlapping_booking_is_rejected(): ...
   ```

   The marker is registered with `--strict-markers`, so a typo fails the run instead of
   silently dropping your test from the traceability matrix.
4. Run `make lint` and `make test` before you push.
5. Open a PR with the template completed, including the AI-usage disclosure.

Generate the traceability matrix at any time:

```bash
docker compose run --rm api python ../scripts/traceability.py tests
```

## Troubleshooting

**`docker compose up` fails: port 5432 already in use.**
Something else owns it — usually a local PostgreSQL install or another project's
container. Set `POSTGRES_PORT=5433` in your `.env` and start again; only the host-side
port changes, and nothing inside the stack is affected. For 8000 or 5173, change the host
side of the mapping in `docker-compose.yml`.

**The web page says "Cannot reach the API".**
Check the API is healthy with `docker compose ps` and
`curl http://localhost:8000/health`. `docker compose logs api` usually says why. The API
waits for the database before starting, so this normally means a migration failed.

**`make seed` (or any `docker compose run ... /scripts/...`) fails with "Files/Git/app: not found".**
Git Bash on Windows rewrites paths like `/app` into `C:/Program Files/Git/app` before Docker
sees them. Run the command from PowerShell, or prefix it with `MSYS_NO_PATHCONV=1`.

**Migrations fail, or the database is in a strange state.**
`docker compose down -v && docker compose up --build` deletes the volume and rebuilds the
schema from migration 0001. This is safe — there is no local data worth keeping.

**The API restarts in a loop with a settings validation error.**
A required environment variable is missing. Compare your `.env` with `.env.example`.

**Frontend changes are not showing up.**
The `node_modules` inside the container is separate from anything on your host. After
changing `package.json`, rebuild with `docker compose up --build web`.

**`make: command not found` (Windows).**
Use the plain commands in the table above, or run the repository from WSL.
