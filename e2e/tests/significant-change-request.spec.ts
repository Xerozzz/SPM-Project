import { expect, type Page, test } from '@playwright/test'

import {
  API,
  type ApprovedEvent,
  createApprovedEvent,
  tokenFor,
  VENUE_SPEC_ACCOUNT,
} from '../support/approved-event'

// SCRUM-37: after submission the owning Organiser proposes a significant change instead of
// editing, and the assigned Coordinator sees the proposed value next to the current one.
// Each test makes its own Approved event (attendance 30, layout "Theatre style"), owned by
// VENUE_SPEC_ACCOUNT and assigned to coordinator@example.com, so a re-run never meets an
// earlier run's change or pending requests. Proposing changes nothing on the event.

const COORDINATOR = 'coordinator@example.com'

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

function ownRow(page: Page, name: string) {
  return page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name, exact: true }) })
}

function coordinatorCard(page: Page, name: string) {
  return page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name, exact: true }) })
}

/** The event the current test made, so the hand-back below can find it. */
let event: ApprovedEvent | undefined

// The owner and the assignee must be different people: the owner may also read change
// requests, so one account in both roles would not prove the assigned Coordinator sees
// them. Once the test is done the Lead hands the event back to VENUE_SPEC_ACCOUNT, which
// no other spec signs in as, so it does not stay on coordinator@'s review page. This
// runs when a test fails too.
//
// Accepted trade-off: VENUE_SPEC_ACCOUNT is in the same organisation as organiser@, so
// these events also appear in organiser@'s Organisation calendar, which every organiser@
// spec loads. They are calendar rows only (name, dates, status); a database reset clears
// them.
test.afterEach(async ({ request }) => {
  if (!event) return
  const lead = await tokenFor(request, 'coordinator-lead@example.com')
  const headers = { Authorization: `Bearer ${lead}` }
  const coordinators = (await (
    await request.get(`${API}/api/event-requests/assignable-coordinators`, { headers })
  ).json()) as { id: string; email: string }[]
  const id = (email: string) => coordinators.find((row) => row.email === email)?.id
  const response = await request.post(`${API}/api/event-requests/${event.id}/reassign`, {
    headers,
    data: {
      coordinator_id: id(VENUE_SPEC_ACCOUNT),
      expected_current_coordinator_id: id(COORDINATOR),
    },
  })
  expect(response.ok(), `hand-back -> ${response.status()}`).toBe(true)
  event = undefined
})

const REASON = `E2E more sign-ups ${Date.now()}`

// TC-37-01
test('an organiser proposes a change and the coordinator can compare it', async ({ page }) => {
  event = await createApprovedEvent(page.request, {
    name: `E2E change proposal ${Date.now()}`,
    lane: 0,
    coordinator: COORDINATOR,
  })
  await signIn(page, VENUE_SPEC_ACCOUNT)
  await page.getByRole('button', { name: 'My Events' }).click()
  const row = ownRow(page, event.name)
  await row.getByRole('button', { name: `View details for ${event.name}` }).click()
  await row.getByRole('button', { name: `Propose a change to ${event.name}` }).click()
  const form = row.getByRole('form', { name: 'Propose a change' })

  // AC4: an invalid value is refused and nothing is recorded.
  await form.getByLabel('Attendance').fill('0')
  await form.getByLabel('Reason for the change').fill(REASON)
  await form.getByRole('button', { name: 'Send change request' }).click()
  await expect(form.getByRole('alert')).toContainText('must be a positive whole number')
  await expect(row.getByRole('article').filter({ hasText: REASON })).toHaveCount(0)

  // AC1, AC3: a valid proposal is recorded as pending, with the current value kept.
  await form.getByLabel('Attendance').fill('220')
  await form.getByRole('button', { name: 'Send change request' }).click()
  await expect(form.getByRole('status')).toContainText('Change request sent')
  const proposal = row.getByRole('article').filter({ hasText: REASON })
  await expect(proposal).toContainText('Pending review')
  await expect(proposal.getByRole('row').filter({ hasText: 'Attendance' })).toContainText('30')
  await expect(proposal.getByRole('row').filter({ hasText: 'Attendance' })).toContainText('220')
  await page.getByRole('button', { name: 'Sign out' }).click()

  // AC5, AC6: the coordinator sees the same pending request, and the event is unchanged.
  await signIn(page, COORDINATOR)
  await page.getByRole('button', { name: 'Review Queue' }).click()
  const card = coordinatorCard(page, event.name)
  await card.getByRole('button', { name: `View details for ${event.name}` }).click()
  await expect(card.getByText(REASON)).toBeVisible()
  await expect(card.getByText('Attendance:').locator('..')).toContainText('30')
})

// SCRUM-47: the assigned Coordinator approves a pending change with a note, and the
// event's own value changes while the request shows what was applied.
const LAYOUT_REASON = `E2E new layout ${Date.now()}`

// TC-47-01
test('the coordinator approves a change and it is applied', async ({ page }) => {
  event = await createApprovedEvent(page.request, {
    name: `E2E change approval ${Date.now()}`,
    lane: 1,
    coordinator: COORDINATOR,
  })
  await signIn(page, VENUE_SPEC_ACCOUNT)
  await page.getByRole('button', { name: 'My Events' }).click()
  const row = ownRow(page, event.name)
  await row.getByRole('button', { name: `View details for ${event.name}` }).click()
  await row.getByRole('button', { name: `Propose a change to ${event.name}` }).click()
  const form = row.getByRole('form', { name: 'Propose a change' })
  await form.getByLabel('Layout').fill('Cabaret style')
  await form.getByLabel('Reason for the change').fill(LAYOUT_REASON)
  await form.getByRole('button', { name: 'Send change request' }).click()
  await expect(form.getByRole('status')).toContainText('Change request sent')
  await page.getByRole('button', { name: 'Sign out' }).click()

  await signIn(page, COORDINATOR)
  await page.getByRole('button', { name: 'Review Queue' }).click()
  const card = coordinatorCard(page, event.name)
  await card.getByRole('button', { name: `View details for ${event.name}` }).click()
  const request = card.getByRole('article').filter({ hasText: LAYOUT_REASON })
  await request.getByLabel('Decision note').fill('Cabaret fits the hall')
  await request.getByRole('button', { name: 'Approve change' }).click()

  await expect(request).toContainText('Approved')
  await expect(request).toContainText('Cabaret fits the hall')
  await expect(request.getByRole('row').filter({ hasText: 'Layout' })).toContainText('Applied')
  await expect(card.getByText('Layout:').locator('..')).toContainText('Cabaret style')
})
