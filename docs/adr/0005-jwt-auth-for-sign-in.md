# ADR-0005: JWT bearer auth with role claims for sign-in

- **Status:** Proposed — password-hashing library superseded by ADR-0007
- **Date:** 2026-09-12
- **Deciders:** Alvin
- **Related stories:** SCRUM-27 (F1)

## Context

F1 requires sign-in against supplied user data only. No self-registration. Accounts carry one or more roles. Unauthenticated access redirects to sign-in; sign-out must invalidate the session.

## Decision

We will use JWT bearer tokens with role claims, bcrypt password hashing via `passlib`, generic invalid-credentials errors, and stateless sign-out (client discards token).

No new runtime dependencies: `pyjwt` and `passlib[bcrypt]` are already in `api/requirements.txt`.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Server-side sessions | Requires session store; conflicts with stateless API and teardown/setup rule |
| OAuth / external IdP | Out of scope for F1; supplied user data only |

## Consequences

**Good**
- Matches stack choice in `AGENTS.md` §2.
- Role claims enable shared `require_role` dependency.

**Bad / accepted trade-offs**
- No server-side revocation; sign-out is client-side discard until refresh/blacklist story.
- Seed users must ship in migration/seed SQL, not manual inserts.

**What this makes harder to change later**
- Switching to sessions or OAuth needs a superseding ADR.

## Notes

- `api/core/config.py` already defines `jwt_secret` and `jwt_expiry_minutes`.
