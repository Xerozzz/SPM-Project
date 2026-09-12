# ADR-0007: Hash passwords with bcrypt directly, not through passlib

- **Status:** Proposed
- **Date:** 2026-09-12
- **Deciders:** Yi Terng (author), Alvin (SCRUM-27 author), whole team at review
- **Related stories:** SCRUM-27 (F1 sign-in)

## Context

AGENTS.md §2 and ADR-0005 name `passlib[bcrypt]` for password hashing, and the scaffold
listed it in `requirements.txt`. The SCRUM-27 implementation imported `bcrypt` directly
instead. That left the code and the record disagreeing, and `bcrypt` — the library the
code actually depends on — was only present as a transitive dependency of a package
nothing imports.

The deviation was the right call. passlib's last release (1.7.4, 2020) predates bcrypt 4.1,
which removed the `__about__` module passlib reads at import; on current bcrypt it logs an
error on every import and its wrapper is one release away from breaking outright. Our own
review also found that bcrypt ≥ 5 raises `ValueError` for passwords over 72 bytes rather
than truncating, which had to be handled in our code either way.

## Decision

We will hash and verify passwords with the `bcrypt` package directly, in
`api/core/security.py`, and declare it explicitly in `api/requirements.txt`. `passlib` is
removed. Passwords longer than 72 bytes are treated as a wrong password (`verify_password`
returns `False`), never as an error.

This supersedes the hashing-library sentence of ADR-0005; everything else in ADR-0005
(JWT bearer, role claims, generic errors, client-side sign-out) stands.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep `passlib[bcrypt]` as written | Unmaintained; already logs an error against current bcrypt; adds a wrapper layer nobody can explain in the Q&A |
| `argon2-cffi` | Arguably the better algorithm, but a new dependency and a change to the agreed stack for no requirement we have |
| Leave the code as it was and only fix the ADR | Would keep `bcrypt` as an undeclared transitive dependency — a `pip install` that drops passlib would silently break sign-in |

## Consequences

**Good**
- `requirements.txt` names what the code imports; one fewer package in the image.
- Two lines of hashing code that every team member can read.

**Bad / accepted trade-offs**
- Anyone reading AGENTS.md §2 sees "passlib"; update that table at the next retrospective.
- Changing algorithm later means writing a migration path ourselves (passlib offered
  multi-scheme verification). Unlikely to matter within this module.

**What this makes harder to change later**
- Nothing beyond the point above.
