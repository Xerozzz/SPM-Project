import { expect, type Locator, type Page, test } from '@playwright/test'

import {
  API,
  type ApprovedEvent,
  createApprovedEvent,
  createAssignedEvent,
  tokenFor,
  VENUE_SPEC_ACCOUNT,
} from '../support/approved-event'

// SCRUM-88: an event's history, oldest first, shown to the owner and the assigned
// Coordinator, with internal notes only for the Coordinator (ADR-0062). Each test makes its
// own uniquely named event, owned by VENUE_SPEC_ACCOUNT and assigned to coordinator@, so the
// owner and the assignee are different people and a re-run never meets an earlier event.

const COORDINATOR = 'coordinator@example.com'
const LEAD = 'coordinator-lead@example.com'

/** The event the current test made, so the hand-back below can find it. */
let event: ApprovedEvent | undefined

// Once the test is done the Lead hands the event back to VENUE_SPEC_ACCOUNT, which no
// other spec signs in as, so it does not stay on coordinator@'s review page. This runs
// when a test fails too (as in significant-change-request.spec.ts).
test.afterEach(async ({ request }) => {
  if (!event) return
  const lead = await tokenFor(request, LEAD)
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

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
}

function ownRow(page: Page, name: string) {
  return page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name, exact: true }) })
}

function cancelledCard(page: Page, name: string) {
  const section = page.getByRole('heading', { name: 'Cancelled events' }).locator('..')
  return section.getByRole('article').filter({ hasText: name })
}

function coordinatorCard(page: Page, name: string) {
  return page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name, exact: true }) })
}

/** Opens the event history inside `scope` and returns its entries, oldest first. */
async function openHistory(scope: Locator): Promise<Locator> {
  await scope.getByRole('button', { name: 'View event history' }).click()
  const panel = scope.getByText('Event history', { exact: true }).locator('..')
  return panel.getByRole('listitem')
}

test('the owner sees creation, submission, assignment and approval in order', async ({
  page,
  request,
}) => {
  const stamp = Date.now()
  event = await createApprovedEvent(request, {
    name: `E2E history ${stamp}`,
    lane: 0,
    coordinator: COORDINATOR,
  })

  await signIn(page, VENUE_SPEC_ACCOUNT)
  await page.getByRole('button', { name: 'My Events' }).click()
  const row = ownRow(page, event.name)
  await row.getByRole('button', { name: `View details for ${event.name}` }).click()
  const entries = await openHistory(row)

  await expect(entries).toHaveText([
    new RegExp(`^Draft created by ${VENUE_SPEC_ACCOUNT}`),
    new RegExp(`^Submitted for review by ${VENUE_SPEC_ACCOUNT}`),
    new RegExp(`^Coordinator assigned by ${LEAD}`),
    new RegExp(`^Coordinator review: approved by ${COORDINATOR}`),
  ])
  await expect(entries.filter({ hasText: 'Internal note' })).toHaveCount(0)
})

test('an internal note appears for the assigned Coordinator and never for the owner', async ({
  page,
  request,
}) => {
  const stamp = Date.now()
  const note = `E2E history note ${stamp}: check the fire exits`
  // Notes can only be recorded while the event is Submitted, so it is not approved.
  event = await createAssignedEvent(request, {
    name: `E2E history note ${stamp}`,
    lane: 1,
    coordinator: COORDINATOR,
  })

  await signIn(page, COORDINATOR)
  await page.getByRole('button', { name: 'Review Queue' }).click()
  const card = coordinatorCard(page, event.name)
  await card.getByRole('button', { name: `View details for ${event.name}` }).click()
  await card.getByLabel('Internal note', { exact: true }).fill(note)
  await card.getByRole('button', { name: 'Record internal note' }).click()
  await expect(card.getByRole('status').filter({ hasText: 'Message sent' })).toBeVisible()
  const coordinatorView = await openHistory(card)
  const noteEntry = coordinatorView.filter({ hasText: 'Internal note' })
  await expect(noteEntry).toHaveCount(1)
  await expect(noteEntry).toContainText(`by ${COORDINATOR}`)
  await expect(noteEntry).toContainText(`Note: ${note}`)
  await signOut(page)

  await signIn(page, VENUE_SPEC_ACCOUNT)
  await page.getByRole('button', { name: 'My Events' }).click()
  const row = ownRow(page, event.name)
  await row.getByRole('button', { name: `View details for ${event.name}` }).click()
  const ownerView = await openHistory(row)
  await expect(ownerView).toHaveText([
    /^Draft created/,
    /^Submitted for review/,
    /^Coordinator assigned/,
  ])
  await expect(row.getByText(note)).toHaveCount(0)
  await expect(row.getByText(/Internal note/)).toHaveCount(0)
})

test('the assigned Coordinator and a Lead open a cancelled event history from its list', async ({
  page,
  request,
}) => {
  // SCRUM-88 AC6. Not kept in `event`: a cancelled event has left the review page, so the
  // hand-back above is neither needed nor possible.
  const stamp = Date.now()
  const reason = `E2E history cancel ${stamp}: venue withdrawn`
  const cancelled = await createAssignedEvent(request, {
    name: `E2E history cancelled ${stamp}`,
    lane: 2,
    coordinator: COORDINATOR,
  })
  const coordinator = await tokenFor(request, COORDINATOR)
  const response = await request.post(`${API}/api/event-requests/${cancelled.id}/cancel`, {
    headers: { Authorization: `Bearer ${coordinator}` },
    data: { reason },
  })
  expect(response.ok(), `cancel -> ${response.status()}`).toBe(true)

  for (const viewer of [COORDINATOR, LEAD]) {
    await signIn(page, viewer)
    await page
      .getByRole('button', { name: viewer === LEAD ? 'Active Assignments' : 'Review Queue' })
      .click()
    const card = cancelledCard(page, cancelled.name)
    await expect(card).toContainText(`Reason: ${reason}`)
    const entries = await openHistory(card)
    await expect(entries.last()).toContainText(`Event cancelled by ${COORDINATOR}`)
    await signOut(page)
  }
})
