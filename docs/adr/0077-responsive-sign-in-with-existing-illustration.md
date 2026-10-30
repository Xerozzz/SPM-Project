# ADR-0077: Present sign-in beside the existing team illustration

- **Status:** Proposed
- **Date:** 2026-10-30
- **Deciders:** Sheryl (requested the sign-in improvements), whole team at review
- **Related stories:** SCRUM-27 (F1 sign-in)
- **Extends:** ADR-0005 (presentation only)

## Context

The sign-in page has little product identity and faint input boundaries. The repository
already contains an illustration suited to event coordination. Supplied-account sign-in,
generic credential errors and the existing session behaviour must remain intact.

## Decision

We will use a desktop split layout with a mint brand panel and the existing illustration.
Smaller screens show the form and compact branding. Sign-in receives local field borders,
taller controls, clearer copy and a labelled password visibility toggle. Passwords start
hidden; toggling preserves the value and never submits the form. Auth dependencies and
the shared field styles are unchanged.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Keep the single centred card | Does not provide the requested illustration and brand presence |
| Show the large illustration on mobile | Pushes sign-in controls further down the screen |
| Restyle the shared input class | Would change every form as part of a sign-in-only story |

## Consequences

**Good**
- Reuses an existing asset without a new dependency or authentication path.
- Keeps sign-in compact on small screens and makes fields easier to distinguish.

**Bad / accepted trade-offs**
- The illustration adds an image request on desktop and is decorative, with empty alt text.
- Password text is visible after the user explicitly chooses Show password.

**What this makes harder to change later**
- A future global input redesign should reconcile the local sign-in sizing and borders.
