# Sprint 4 — Alvin

## Scope and intent

This is the implementation and test handoff for Alvin's nine Jira Stories in **SCRUM Sprint 4**
and one deferred backlog story after the 19 October 2026 split. It follows the Sprint 3
handoff's one-story-per-branch format.
Jira remains the source of truth if a story is refined later; reconcile any change before coding.

These stories extend existing venue requests, tentative holds and the private notification
inbox. Reuse those flows. Do not build another booking system, final-confirmation flow, expiry
worker or notification inbox. Deliver one Jira Story per branch and pull request.

## Shared story completion checklist

Every new agent must read this checklist and the handoff log first. Continue with an unchecked,
dependency-ready story. Do not redo a checked story unless a regression or review comment
requires it.

- [x] **SCRUM-110** — Venue approval creates a Tentative hold
- [x] **SCRUM-121** — Venue Staff update an active hold's current expiry
- [ ] **SCRUM-111** — Existing venue requests carry session labels and independent periods
- [ ] **SCRUM-49** — Venue Staff receive new-request notifications
- [ ] **SCRUM-124** — Technical Support receive equipment-requirement notifications
- [ ] **SCRUM-125** — Coordinator receives equipment review/reservation outcomes
- [ ] **SCRUM-122** — Coordinator receives venue decision/expiry-update notifications
- [ ] **SCRUM-123** — Venue Staff receive single-arrangement cancellation notifications
- [ ] **SCRUM-127** — Venue Staff receive revised-request notifications

**Deferred in the backlog**

- [ ] **SCRUM-126** — Coordinator receives reservation-reconsideration notifications;
  waits for SCRUM-117's source action

### Checklist update protocol

Change `[ ]` to `[x]` only when every Jira acceptance criterion and mapped test case passes,
the relevant migration and ADR are present, the required lint and test checks pass, and the
change is review-ready as one story's pull request. The repository Definition of Done additionally
requires team/PO demonstration, teammate approval and merge to `main`; record these separately
in the log rather than claiming the story is formally Done before they happen.

For partial or blocked work, leave the box unchecked and append a handoff row with what is
complete, what remains, the branch/PR, any failing check, and the next safe step. Never tick a
story merely because code was generated or committed.

### Completion and handoff log

Append a row whenever an agent completes or pauses a story. Keep previous rows; this is an
append-only work log.

| Date (SGT) | Story | State | Branch / PR | Agent handoff note |
|---|---|---|---|---|
| 20 Oct 2026 | SCRUM-121 | Review-ready | `feat/SCRUM-121-update-active-hold-expiry` / PR not opened | Active Tentative hold expiry update implemented with UTC validation, booking-row locking, rollback safety, Venue Staff UI and persisted reload coverage. `make lint`, `make test` (1,214 backend at 98.48%; 312 frontend) and the focused Playwright flow pass. No schema change, migration, dependency or ADR required. |

## Estimate and delivery overview

| Order | Jira Story | Outcome | Points | Depends on |
|---:|---|---|---:|---|
| 1 | [SCRUM-110](https://spm-is212.atlassian.net/browse/SCRUM-110) | Approval creates a Tentative hold | 3 | Existing SCRUM-83, SCRUM-108 and SCRUM-82 flows |
| 2 | [SCRUM-121](https://spm-is212.atlassian.net/browse/SCRUM-121) | Active hold expiry can be updated | 3 | SCRUM-110 |
| 3 | [SCRUM-111](https://spm-is212.atlassian.net/browse/SCRUM-111) | Session label and period travel through venue requests | 5 | Existing SCRUM-78 and buffer/conflict paths; integrate with SCRUM-110 |
| 4 | [SCRUM-49](https://spm-is212.atlassian.net/browse/SCRUM-49) | Venue Staff learn of a new request | 1 | Existing request submission, SCRUM-99 inbox |
| 5 | [SCRUM-124](https://spm-is212.atlassian.net/browse/SCRUM-124) | Technical Support learn of new/changed equipment needs | 2 | SCRUM-43, SCRUM-44 actions |
| 6 | [SCRUM-125](https://spm-is212.atlassian.net/browse/SCRUM-125) | Coordinator learns equipment review/reservation outcomes | 3 | SCRUM-44, SCRUM-52, SCRUM-53 actions |
| 7 | [SCRUM-122](https://spm-is212.atlassian.net/browse/SCRUM-122) | Coordinator learns venue decision/expiry outcomes | 3 | SCRUM-110, SCRUM-121 |
| 8 | [SCRUM-123](https://spm-is212.atlassian.net/browse/SCRUM-123) | Venue Staff learn of one arrangement's cancellation | 1 | SCRUM-109 |
| 9 | [SCRUM-127](https://spm-is212.atlassian.net/browse/SCRUM-127) | Venue Staff learn of a revised request | 1 | Upstream revised-request source action |
| Backlog | [SCRUM-126](https://spm-is212.atlassian.net/browse/SCRUM-126) | Coordinator learns reservation reconsideration state | 2 | SCRUM-117, outside Sprint 4 |

**Re-estimated Sprint 4 total: 22 story points**, plus 2 points deferred to the backlog.
Use only [SCRUM-96](https://spm-is212.atlassian.net/browse/SCRUM-96), a completed
1-point Sprint 3 story, as the relative anchor: it added one committed notification
trigger with active-recipient routing, retry deduplication and rollback safety on the
existing inbox. SCRUM-49, SCRUM-123 and SCRUM-127 each have one comparable trigger
(1 point). SCRUM-124 and SCRUM-126 cover two action paths (2 points); SCRUM-122 covers
approval, rejection and expiry updates (3 points); SCRUM-125 covers equipment review
and reservation actions (3 points). SCRUM-110 changes the approval state and UI with
concurrency protection (3 points). SCRUM-121 updates an active hold's current expiry
with validation, concurrency protection and staff UI (3 points), while SCRUM-111 propagates session data across request, search, conflict,
calendar and UI paths (5 points). Confirm these relative estimates with the team.
SCRUM-110 and SCRUM-111 may be developed
independently where code does not collide, then integrated. A blocked notification trigger
must not hold up the other notification stories. As of 19 October, SCRUM-109, SCRUM-117 and
the controlled venue-change paths are To Do; test their alerts against real source actions
when those paths land. SCRUM-126 stays in the backlog until SCRUM-117 is planned.

## Rules for every implementation agent

1. Read `AGENTS.md`, `docs/DEFINITION_OF_DONE.md` and `docs/adr/README.md` before design or code.
   Read the applicable ADRs, especially ADR-0002, ADR-0017, ADR-0019, ADR-0022, ADR-0026,
   ADR-0029 and ADR-0030. ADR-0035 applies to Coordinator access. Check the index for newer
   or superseding decisions before editing.
2. Work on exactly one Jira Story per branch and PR, named `feat/<JIRA-KEY>-short-description`.
   Keep the non-generated diff below the repository's approximate 400-line review threshold;
   refine an oversized story visibly instead of hiding a large change in one PR.
3. Test-first: write the story's failing tests, see the intended failure, then implement.
   Put each backend test under `@pytest.mark.story("<JIRA-KEY>")`; include the key in frontend
   and Playwright test names.
4. Keep routers thin, services responsible for orchestration, repositories responsible for
   persistence, and pure rules in `api/domain/`. Use shared authorization dependencies.
5. Store and compare timezone-aware UTC instants. Convert for display only in the UI.
   Schema changes require a new Alembic migration; never edit a merged migration. Record a
   new or superseding ADR when the architectural decision rules require one.
6. Do not delete, weaken, skip or mark tests `xfail` to force a green build. For a changed
   business rule, update the old expectation and add regression tests showing the new rule.
7. Run targeted tests during development, then `make lint`, `make test`, frontend tests and
   relevant Playwright tests before requesting review. Record any unavailable check in the log.
8. Disclose AI assistance in the PR template. The contributor must understand every changed
   line and link the Jira Story and any new/superseding ADR in the PR.
9. After review-ready completion, tick the shared box and append a log row in the same branch.

## Common test design rules

- `Level` means **Unit**, **Integration** or **E2E**. Boundary, authorization, rollback and
  concurrency describe the test focus, not another level.
- Map every acceptance criterion to at least one test. Cover a normal case, a boundary,
  an unauthorized call, an invalid state and a conflict or rollback where relevant.
- For lists and recipient sets, exercise zero, one and many records. For time-dependent
  actions, fix the clock in tests and check equality at important boundaries.
- Verify persisted rows and unchanged rows, not only HTTP status or rendered text.
- Keep old whole-event booking and unrelated notification behavior covered when adding new
  session or trigger paths.

## SCRUM-110 — Change venue approval to create a Tentative hold

**Jira:** [SCRUM-110](https://spm-is212.atlassian.net/browse/SCRUM-110) · **3 provisional points** ·
**Status on 19 October:** To Do

### User story

As Venue Staff, I want approving a Pending request to create a time-limited Tentative hold
so the later event-confirmation step remains with the assigned Coordinator.

### Acceptance criteria

1. Approval requires a timezone-aware expiry strictly after the action instant and no later
   than the booking start. Return a field error for invalid input without changing the row.
2. Change the existing Pending booking row to Tentative, retaining its venue, event, selected
   session period, approving staff and UTC action time.
3. Reuse existing buffered occupancy, database conflict protection and SCRUM-108 expiry
   processing, retained record and single expiry alert. Pending requests do not occupy venues.
4. Remove direct Venue Staff confirmation through the existing API and UI, whether the row
   starts Pending or Tentative. SCRUM-80 owns later event confirmation.
5. Concurrent approval, conflict, invalid state or rollback leaves no partial hold. SCRUM-121
   owns expiry editing; SCRUM-122 owns approval notifications.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-110-01 | Unit | At a fixed UTC instant, reject naive, missing, now-or-earlier and after-booking-start expiry; accept one instant after now and exactly booking start. |
| TC-110-02 | Integration | Venue Staff approve Pending with valid expiry; the same row becomes Tentative with preserved venue/event/session period, actor and time, and blocks a buffered overlap. |
| TC-110-03 | Integration | Every former direct-confirmation API path is removed, refused or redirected to hold semantics; neither Pending nor Tentative can become Confirmed by Venue Staff. |
| TC-110-04 | Integration | Non-staff, unauthenticated, invalid-state, conflicting and concurrent approval attempts leave no partial hold or decision; the exclusion constraint still wins races. |
| TC-110-05 | Integration | The existing expiry worker expires the approved hold once, retains its record and notifies the current Coordinator once. |
| TC-110-06 | Unit | Staff UI requires expiry for approval and offers no direct confirmation control; validation and recoverable errors are shown. |
| TC-110-07 | E2E | Staff approve a Pending request; it appears as Tentative, not Confirmed, after reload. |

### Agent implementation instructions

- Start at `api/services/venue_bookings.py`, `api/routers/venue_bookings.py`,
  `api/routers/venue_booking_decisions.py` and `api/domain/venue_hold.py`.
  Existing `approve()` directly confirms, while `hold()` already creates Tentative.
  Converge the routes on one approval-to-hold contract.
- Update the staff API wrapper and `web/src/components/VenueBookingDecisions.tsx`.
  Replace tests of the superseded direct-confirmation behavior with the new rule.
- Keep this PR limited to approval behavior and compatibility with the existing expiry worker.
  The SCRUM-121 expiry-edit action and SCRUM-122 notification trigger belong in their own PRs.

---

## SCRUM-121 — Update an active venue hold's current expiry

**Jira:** [SCRUM-121](https://spm-is212.atlassian.net/browse/SCRUM-121) · **3 estimated points** ·
**Status on 19 October:** To Do

### User story

As Venue Staff, I want to revise an active Tentative hold's expiry so the Coordinator
has the agreed time to finalise arrangements.

### Acceptance criteria

1. Only Venue Staff may update an active Tentative hold. Current expiry appears in existing
   authorised booking/hold views.
2. The new expiry is timezone-aware, strictly after the action instant and no later than
   booking start. Invalid input produces a field error and no mutation.
3. A hold whose old expiry is at or before the action instant cannot be revived. Pending,
   Expired, Confirmed, Cancelled and Rejected rows cannot use the update.
4. A successful edit updates the current expiry on the hold. No separate expiry-change
   history is required.
5. Concurrent edits or expiry produce one valid serial outcome; failed changes leave the
   hold unchanged. Reuse SCRUM-108's worker and expiry alert. SCRUM-122 later owns the
   successful-update alert.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-121-01 | Unit | Reject naive, now-or-earlier and after-booking-start expiry; accept the exact booking-start boundary when it is future. |
| TC-121-02 | Integration | Update an active hold twice; the hold keeps the latest current expiry after each edit and no separate expiry-change record is created. |
| TC-121-03 | Integration | Updating exactly at or after the old expiry cannot revive the hold; the existing expiry worker can expire it and alert once. |
| TC-121-04 | Integration | Non-staff and unauthenticated callers, plus Pending, Expired, Confirmed, Cancelled and Rejected rows, are refused without changing the expiry. |
| TC-121-05 | Integration | Two sessions edit/expire the same row; status and current expiry agree on the serial winner. A forced rollback leaves the hold unchanged. |
| TC-121-06 | Unit | Staff UI exposes expiry editing only for active Tentative holds and shows validation, success and recoverable error states. |
| TC-121-07 | E2E | Staff edit a hold expiry and reload; the current value remains visible and the hold still expires via the existing worker. |

### Agent implementation instructions

- Reuse `api/domain/venue_hold.py` validation, `api/services/venue_hold_expiry.py`
  and row-locking paths in `api/repositories/venue_availability.py`. Validate the
  locked row at one supplied UTC action time.
- Update the existing hold row rather than adding an expiry-change table or migration.
  Check service commit boundaries against the existing expiry worker.
- Update the existing authorised hold views and Venue Staff controls. Do not add a
  second expiry worker, duplicate SCRUM-108 alerts or implement SCRUM-80 confirmation.

---

## SCRUM-111 — Add session labels and independent periods to venue requests

**Jira:** [SCRUM-111](https://spm-is212.atlassian.net/browse/SCRUM-111) · **5 points** ·
**Status on 19 October:** To Do

### User story

As the assigned Event Coordinator, I want to label each session and choose its venue-request
period independently so the existing multiple-venue workflow supports shorter and parallel
sessions.

### Acceptance criteria

1. Extend the existing venue-request form/API with a distinguishable, non-blank session label
   and timezone-aware start/end values. Only the current assigned Coordinator may submit in
   the permitted planning state.
2. End is strictly after start. The selected period lies within the parent event period;
   exact parent start/end boundaries are allowed. Bad input creates no request.
3. Store the selected period on the existing `venue_bookings` row. Sessions may cover only
   part of an event and may overlap at different venues.
4. Use the selected period in venue search, availability, buffered conflict checks, Venue
   Staff decisions and calendar entries. Reuse suitability against the event's recorded
   requirements; do not invent per-session attendance or a second suitability engine.
5. Keep multiple requests independent: requesting or deciding one does not mutate the
   others. Occupied intervals at the same venue still conflict. Existing whole-event rows
   retain their recorded periods.
6. Display the label and actual period to both Coordinator and Venue Staff. Apply the
   venue's existing setup/turnaround rules; do not add per-booking buffer overrides.
7. Continue refusing direct edits after event confirmation. SCRUM-37/SCRUM-47 own the later
   controlled change flow; SCRUM-116 owns later replacement reuse.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-111-01 | Unit | Reject blank/whitespace label, naive datetimes, equal or reversed start/end, and periods outside either parent boundary; exact parent boundaries and a shorter internal period pass. |
| TC-111-02 | Integration | Assigned Coordinator submits a labelled shorter session; existing booking row stores supplied UTC start/end and label, not copied parent times. |
| TC-111-03 | Integration | Submit zero, one and several sessions, including parallel periods at different venues; each row remains independently addressable and ordered deterministically. |
| TC-111-04 | Integration | Invalid input or wrong planning state creates no booking; unassigned, previous and unrelated Coordinators and unauthenticated callers are refused without details or mutation. |
| TC-111-05 | Integration | Search and availability for a short session use its supplied period; a venue occupied only outside that period remains available, including buffer-boundary cases. |
| TC-111-06 | Integration | Tentative/Confirmed same-venue overlap is refused using effective periods; a touching non-overlap and parallel requests at other venues remain valid. |
| TC-111-07 | Integration | Venue Staff decision view, Coordinator list and calendar show the same label and actual period. Deciding one request leaves sibling rows unchanged. |
| TC-111-08 | Integration | Suitability still uses the parent event's recorded attendance/facilities; no session-specific suitability rule is introduced. |
| TC-111-09 | Integration | Pre-existing whole-event booking rows retain their recorded start/end after migration and after new session requests; post-confirmation direct edits remain refused. |
| TC-111-10 | Unit | Coordinator form and staff/request displays show labels, periods, validation, loading and recoverable errors with accessible field names. |
| TC-111-11 | E2E | Coordinator requests short and parallel sessions; staff can distinguish them, approve one into the SCRUM-110 hold flow, and see the correct calendar period. |

### Agent implementation instructions

- Start at `api/schemas/venue_bookings.py`, `api/services/venue_bookings.py`,
  `api/models/venue_booking.py`, `api/repositories/venue_availability.py` and
  `api/routers/venue_bookings.py`. `submit()` currently copies `locked.start_at/end_at`;
  the table already has per-booking `start_at/end_at`. Add only the missing session field
  and propagate supplied times through validation and persistence.
- Inspect `api/services/venue_search.py`, venue availability/calendar schemas and the
  existing conflict/buffer functions for any place that silently assumes the parent
  event period. Keep both the friendly conflict check and the database constraint.
- Update `web/src/components/VenueBookingRequest.tsx`, its API types, Venue Staff views and
  calendar presentation. Do not replace SCRUM-78's multiple-request implementation.
- Preserve existing rows through a new migration with an explicit backwards-compatible
  label strategy. Document any non-obvious schema choice in an ADR. Integrate with
  SCRUM-110's approval response without taking ownership of event finalization.

---

## SCRUM-49 — Notify Venue Staff of a new venue request

**Jira:** [SCRUM-49](https://spm-is212.atlassian.net/browse/SCRUM-49) · **1 provisional point** ·
**Status on 19 October:** To Do

### User story

As responsible Venue Staff, I want an inbox alert when a new venue request needs review.

### Acceptance criteria

1. A committed new Pending request alerts responsible active Venue Staff. If no explicit
   responsibility map exists, use active staff in the review role. Zero eligible recipients
   does not fail submission.
2. Identify the event, arrangement, action and UTC time with an authorised review link.
   Include no private clarification content.
3. Deduplicate overlapping roles and retries by recipient/source action. Inactive and
   unrelated users get none; invalid, unauthorised or rolled-back submissions create none.
4. Reuse SCRUM-99's private inbox. A Pending request still does not occupy the venue.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-49-01 | Integration | Zero, one and many eligible Venue Staff receive zero, one or one-each alerts; zero recipients do not fail submission. |
| TC-49-02 | Integration | Inactive/unrelated accounts receive none; a multi-role account gets one; retrying the same request does not duplicate it. |
| TC-49-03 | Integration | Invalid, unauthorised or rolled-back submission creates no alert and no venue occupancy. |
| TC-49-04 | Unit | Inbox item identifies the request and has an accessible authorised route without private notes. |
| TC-49-05 | E2E | Coordinator submits; Venue Staff see one review alert, unrelated users see none. |

### Agent implementation instructions

- Stage notifications in the existing venue-request submission transaction using
  `api/repositories/notifications.py`; reuse SCRUM-99's inbox and access rules.
- This key now owns **new** requests only. SCRUM-127 owns revised requests; the other
  F20 triggers have their own stories below.

---

## SCRUM-124 — Notify Technical Support of equipment requirements needing review

**Jira:** [SCRUM-124](https://spm-is212.atlassian.net/browse/SCRUM-124) · **2 estimated points** ·
**Status on 19 October:** To Do

### User story

As Technical Support Staff, I want an inbox alert when an equipment requirement needs review.

### Acceptance criteria

1. A committed new or changed requirement needing review alerts the responsible active
   Technical Support Staff. Use active review-role members if no mapping exists; zero
   eligible recipients does not fail the change.
2. Identify the event, requirement, new/changed action and UTC time with an authorised
   review link. A later distinct change produces another alert.
3. Deduplicate retries and overlapping roles; exclude inactive/unrelated users. Invalid,
   unauthorised or rolled-back changes create none. Notification does not reserve stock.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-124-01 | Integration | New and later changed requirements produce distinct items for eligible Technical Support Staff. |
| TC-124-02 | Integration | Zero/one/many recipients, inactive users and overlapping roles follow the fallback and dedup rules. |
| TC-124-03 | Integration | Retry, invalid edit, unauthorised edit and rollback produce no extra item or stock reservation. |
| TC-124-04 | Unit | Item identifies requirement/action/time and opens an authorised review view. |
| TC-124-05 | E2E | Coordinator changes a requirement; Technical Support sees the review alert. |

### Agent implementation instructions

- Add triggers to SCRUM-43's committed add/update paths and reuse SCRUM-44's
  Pending Review state. Keep recipient selection and notification staging in the
  source transaction; do not build another requirement store or inbox.

---

## SCRUM-125 — Notify Coordinator of equipment review and reservation outcomes

**Jira:** [SCRUM-125](https://spm-is212.atlassian.net/browse/SCRUM-125) · **3 estimated points** ·
**Status on 19 October:** To Do

### User story

As the assigned Coordinator, I want to know when Technical Support reviews or reserves
equipment for my event.

### Acceptance criteria

1. Committed Available, Partially Available and Unavailable review results each notify
   the current assigned Coordinator with the requirement, outcome and UTC action time.
2. Full and partial reservations each notify that Coordinator with the arrangement,
   quantity/outcome and UTC time.
3. Items link to an authorised record. Distinct later actions create distinct items;
   retries, invalid actions and rollbacks do not. Former/unrelated users get none.
4. Reuse SCRUM-99's inbox; reconsideration transitions belong to SCRUM-126.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-125-01 | Integration | Each of the three review outcomes creates one correctly typed Coordinator alert. |
| TC-125-02 | Integration | Full and partial reservation create separate arrangement-specific alerts. |
| TC-125-03 | Integration | Reassignment changes the recipient for later actions; former/unrelated users get none. |
| TC-125-04 | Integration | Retry, invalid action and rollback create no extra rows; later distinct actions do. |
| TC-125-05 | Unit | Inbox shows requirement, outcome, time and authorised route accessibly. |
| TC-125-06 | E2E | Technical Support reviews and reserves; current Coordinator sees both outcomes. |

### Agent implementation instructions

- Attach to SCRUM-44 and SCRUM-53's committed review/reservation paths.
  SCRUM-52's availability check is read-only, so it is not a notification source
  by itself. Do not alter availability or stock-reservation rules.
- Resolve the current Coordinator at the action's commit, and use distinct action
  identities for repeated decisions on one requirement.

---

## SCRUM-122 — Notify Coordinator of venue decisions and hold expiry updates

**Jira:** [SCRUM-122](https://spm-is212.atlassian.net/browse/SCRUM-122) · **3 provisional points** ·
**Status on 19 October:** To Do

### User story

As the assigned Coordinator, I want alerts when Venue Staff approve, reject or update
the expiry of a venue arrangement.

### Acceptance criteria

1. A committed approval into Tentative, rejection or active-hold expiry update creates
   one distinct alert for the current assigned Coordinator.
2. Identify the venue arrangement, action/outcome and UTC time with an authorised route.
   A later expiry edit creates another alert; retrying one action does not.
3. Former/unrelated recipients get none; invalid, unauthorised and rolled-back actions
   create none. SCRUM-108 alone owns hold-expiry alerts.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-122-01 | Integration | Approval, rejection and expiry edit each create the correct separate item. |
| TC-122-02 | Integration | Two later expiry edits create two source-specific items; retrying one creates none. |
| TC-122-03 | Integration | Reassignment changes later recipient; inactive/unrelated users get none. |
| TC-122-04 | Integration | Invalid action and rollback produce no item; the existing expiry alert is not duplicated. |
| TC-122-05 | Unit | Item names venue, outcome, UTC time and authorised route without private notes. |
| TC-122-06 | E2E | Staff approve and edit a hold; current Coordinator sees both alerts. |

### Agent implementation instructions

- Integrate after SCRUM-110 and SCRUM-121 supply committed source actions.
  Stage rows before each business commit and give each approval, rejection and
  expiry edit a stable unique action identity; a booking ID alone is insufficient.
- Reuse SCRUM-99 and leave SCRUM-108's hold-expiry trigger untouched.

---

## SCRUM-123 — Notify Venue Staff of a single-arrangement cancellation

**Jira:** [SCRUM-123](https://spm-is212.atlassian.net/browse/SCRUM-123) · **1 provisional point** ·
**Status on 19 October:** To Do

### User story

As responsible Venue Staff, I want an alert when the Coordinator cancels one venue
arrangement so I know that space has been released.

### Acceptance criteria

1. A committed SCRUM-109 cancellation of one Pending request, Tentative hold or
   Confirmed booking alerts responsible active Venue Staff. Use active review-role
   staff if no mapping exists; zero eligible staff does not fail cancellation.
2. Identify event, venue arrangement, action/time and authorised route. Do not expose
   private notes, alter sibling bookings or create a whole-event-cancellation alert.
3. Retries deduplicate; invalid, unauthorised and rolled-back cancellations create none.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-123-01 | Integration | Cancel each permitted arrangement state; eligible Venue Staff receive one item. |
| TC-123-02 | Integration | Zero/one/many recipients, inactive users and overlapping roles follow routing rules. |
| TC-123-03 | Integration | Sibling bookings and whole-event cancellation alerts remain unchanged/absent. |
| TC-123-04 | Integration | Retry, invalid action and rollback create no extra item. |
| TC-123-05 | E2E | Coordinator cancels one arrangement; Venue Staff see its alert. |

### Agent implementation instructions

- Wait for SCRUM-109's reusable cancellation source action. Stage the alert in its
  transaction. Keep SCRUM-115's whole-event-cancellation trigger separate.

---

## SCRUM-126 — Notify Coordinator of reservation reconsideration

**Jira:** [SCRUM-126](https://spm-is212.atlassian.net/browse/SCRUM-126) · **2 estimated points** ·
**Status on 19 October:** To Do in backlog; blocked by SCRUM-117

### User story

As the assigned Coordinator, I want to know when an equipment reservation needs
reconsideration and when that concern is resolved.

### Acceptance criteria

1. A committed mark-for-reconsideration action alerts the current Coordinator once.
   A later committed resolution produces its own outcome-specific item.
2. Identify event, requirement/reservation, action/time and authorised destination.
   Former/unrelated recipients get none.
3. Retries, invalid actions and rollbacks create no duplicate or stray items. Reuse
   SCRUM-117's state transitions and SCRUM-99's inbox.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-126-01 | Integration | Mark and resolve produce separate correctly typed items. |
| TC-126-02 | Integration | Reassignment sends later items only to the current Coordinator. |
| TC-126-03 | Integration | Retry, invalid action and rollback create no extra row. |
| TC-126-04 | Unit | Inbox item names arrangement, state and authorised route. |
| TC-126-05 | E2E | After SCRUM-117 changes state, Coordinator sees the matching alert. |

### Agent implementation instructions

- Wait for SCRUM-117's real mark/resolve source operations. Do not fabricate
  reconsideration transitions solely to complete notification tests. Keep this
  story outside Sprint 4 until SCRUM-117 is planned.

---

## SCRUM-127 — Notify Venue Staff of a revised request

**Jira:** [SCRUM-127](https://spm-is212.atlassian.net/browse/SCRUM-127) · **1 provisional point** ·
**Status on 19 October:** To Do

### User story

As responsible Venue Staff, I want an alert when a revised venue request needs review.

### Acceptance criteria

1. A committed revised or replacement request needing review alerts responsible active
   Venue Staff. Use active review-role staff if no mapping exists; zero eligible
   recipients does not fail the change.
2. Identify event, arrangement, revision action/time and authorised review route.
   A Pending revised request alone creates no occupancy.
3. Distinct later revisions create distinct items; retries, invalid actions and
   rollbacks do not. Exclude inactive/unrelated users and private clarification text.

### Required test cases

| Test ID | Level | Scenario and expected result |
|---|---|---|
| TC-127-01 | Integration | A real revised/replacement request creates one item for each eligible staff member. |
| TC-127-02 | Integration | Zero/one/many recipients and role overlap obey routing/dedup rules. |
| TC-127-03 | Integration | Later revision creates another item; retry, invalid action or rollback creates none. |
| TC-127-04 | Integration | Pending revision stays non-occupying and the item links to an authorised view. |
| TC-127-05 | E2E | Staff see and open an alert from the actual controlled revision flow. |

### Agent implementation instructions

- Identify the upstream controlled revision source from SCRUM-37/SCRUM-47 or
  SCRUM-116 before coding. Reuse its committed request operation and SCRUM-99's
  inbox; do not create a second change-management path.
- Keep this blocked story unchecked until the real upstream path can be tested.

## Cross-story architecture instructions

### Booking and time boundaries

- A venue request is a `venue_bookings` row. Pending requests do not occupy a venue;
  Tentative and Confirmed rows do. Compare buffered effective intervals and let the
  PostgreSQL exclusion constraint resolve concurrent overlaps.
- The booking's `start_at/end_at` is the session's requested period once SCRUM-111 lands.
  The parent event period is the allowed outer boundary, not the period to copy on every
  request. The hold expiry is a separate instant, no later than booking start.
- All state/expiry checks must use a single supplied UTC action time within one operation.
  Tests should freeze that instant and exercise exact equality boundaries.

### Transactions and permissions

- Lock a row before changing booking status or expiry. Validate against its locked state.
  Keep story-required audit rows and notifications in the action's transaction, and retain
  the booking record when a hold expires or a decision is later made.
- Assigned-Coordinator access is enforced by shared backend dependencies, not by hiding
  UI controls. Venue Staff and Technical Support actions use their shared role guards.
- Keep one source of truth for each action. SCRUM-110 owns hold approval, SCRUM-121
  owns active-hold expiry edits, SCRUM-111 owns session input/period propagation,
  and SCRUM-49/SCRUM-122–127 each own their named notification trigger.
  SCRUM-80 owns final event confirmation.

### UI behavior

- Show loading, empty, success and recoverable error states. Give date/time inputs and
  notifications accessible names; do not convey state only through color.
- Refresh affected request, staff-review, calendar and inbox queries after successful
  mutations. Only show actions supported by the user's current permissions and state.

## Suggested test locations

Adapt to the existing test layout and avoid duplicate large modules:

- SCRUM-110: `api/tests/unit/test_venue_hold.py`,
  `api/tests/integration/test_venue_holds.py`, `test_confirm_venue_hold.py`,
  `test_expire_venue_holds.py`, Venue Staff component tests and a focused Playwright flow.
- SCRUM-121: hold expiry-edit validation and concurrency integration tests, `test_expire_venue_holds.py`,
  Venue Staff component tests and a focused expiry-edit E2E flow.
- SCRUM-111: `api/tests/integration/test_submit_venue_booking.py`,
  `test_multiple_venue_bookings.py`, `test_venue_search.py`,
  `test_venue_calendar_entry.py`, Coordinator/Staff component tests and a session E2E flow.
- SCRUM-49/SCRUM-122–127: `api/tests/integration/test_notifications.py`
  plus focused tests beside each venue/equipment source action, inbox component
  tests and one recipient-isolation E2E flow per distinct user outcome.

## Completion checklist for each agent

- [ ] Every Jira acceptance criterion has a mapped passing test case.
- [ ] Normal, empty, unauthorized, invalid-state, boundary and relevant race/rollback paths pass.
- [ ] Existing whole-event bookings, buffer conflicts, hold expiry and inbox privacy still pass.
- [ ] Relevant migration/ADR is included; no merged migration was edited.
- [ ] Diff is explainable and within the repository's approximate review threshold.
- [ ] `make lint`, `make test`, frontend tests and relevant E2E tests pass or a precise blocker is logged.
- [ ] Branch, commits, tests and PR title carry the correct Jira key; PR links Jira and ADRs.
- [ ] Shared checkbox and append-only handoff log are updated at review-ready completion.
