# ADR-0003: Layered architecture with an I/O-free domain core

- **Status:** Accepted
- **Date:** 2026-09-08
- **Deciders:** Whole team
- **Related stories:** cross-cutting

## Context

Five developers working in parallel on ten epics, most of them assisted by AI, on a codebase
none of us has seen before. Without an agreed structure, AI-assisted code converges on the
framework's path of least resistance: everything in the route handler. That code works, and it
is nearly impossible to unit test, to review, or to explain as a *design*.

We also have a coverage expectation approaching 100% on the interesting logic, and the
interesting logic here — venue suitability, period overlap, event status transitions — is
genuinely intricate. Testing it through HTTP endpoints against a live database would be slow
and would obscure which rule broke.

## Decision

Four layers, with a strict dependency direction:

```
routers  ->  services  ->  repositories  ->  database
              |
              v
            domain      (pure: no I/O, no ORM, no framework imports)
```

- `routers/` parse, authorise, delegate, serialise. At most ~15 lines each.
- `services/` hold business orchestration and transaction boundaries.
- `repositories/` are the only place SQLAlchemy is imported for queries.
- `domain/` holds pure functions and value objects and is tested to 100%.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Logic in route handlers (FastAPI default style) | Fast at first; untestable without HTTP and a database; produces no explainable design |
| Fat ORM models (active record) | Couples business rules to persistence; makes the rules impossible to test in isolation |
| Full hexagonal architecture with ports and adapters | Defensible, but the ceremony would cost us a sprint we do not have for five developers new to it |

## Consequences

**Good**
- The hard logic is tested in milliseconds without a database, so we can afford exhaustive
  boundary and conflict cases.
- The layering gives the C4 component diagram a real structure to describe.
- It gives AI assistants an unambiguous answer to "where does this code go?", which is most of
  what keeps five assistants consistent.

**Bad / accepted trade-offs**
- More files and more indirection than the framework's default style; simple CRUD stories
  pass through four layers to do very little.
- Requires discipline in review: the failure mode is logic quietly creeping into services'
  repository calls or into routers.

**What this makes harder to change later**
- Little. The domain core is the most portable part of the system by construction.
