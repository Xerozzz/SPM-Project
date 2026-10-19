# ADR-0009: Derive draft visibility from organiser organisation membership

- **Status:** Proposed — visibility rule superseded by ADR-0039
- **Date:** 2026-09-14
- **Deciders:** Sheryl, team review pending
- **Related stories:** SCRUM-29

## Context

SCRUM-29 says a draft belongs to the organiser who created it, but other organisers in the
same client organisation may see it in the shared drafts view. Organisers outside that
organisation and event coordinators must not see the draft before it is submitted.

The existing event request table already has `organiser_id`, which proves ownership. It can
also support same-organisation visibility once users belong to an organisation.

## Decision

We will add a minimal `organisations` table and store `organisation_id` on `users`.

Draft visibility is derived through:

```text
EventRequest.organiser_id -> User.organisation_id
```

We will not duplicate organisation state on `event_requests` for SCRUM-29. The product has no
current user-organisation transfer workflow, so deriving the organisation through the creator is
the smallest explainable model.

Event-request VIEW and EDIT access is centralised in `require_event_access(...)`, not repeated
inside routers. For drafts, the creator organiser can view and edit, same-organisation organisers
can view only, outside-organisation organisers cannot view, and event coordinators cannot view
before submission. Once a request is submitted, event coordinators may view it through the same
shared dependency.

Draft expiry is deliberately not modelled. There is no expiry timestamp, scheduled cleanup, or
retention state in this story.

## Alternatives considered

| Option | Why we rejected it |
|---|---|
| Store `organisation_id` on `event_requests` too | More robust if users can move organisations later, but duplicates state before that workflow exists |
| Add a free-text organisation name to users | Easy to mistype; no foreign key; weak evidence in the Q&A |
| Build full client account management now | Too much scope for SCRUM-29; supplied seed data is enough for this story |

## Consequences

**Good**
- Same-organisation draft visibility has a database-backed fact to check.
- The schema still keeps draft content nullable, so incomplete drafts can be saved.

**Bad / accepted trade-offs**
- This adds a foundational table before a full organisation-management story exists.
- Existing local users need a default organisation during migration.

**What this makes harder to change later**
- If the product later allows users to move organisations, draft visibility rules must decide
  whether drafts follow the organiser or keep their original organisation.
