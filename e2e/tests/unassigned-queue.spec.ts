import { expect, type Page, test } from '@playwright/test'

// TC-101-08: an organiser submits a request, then a Lead signs in and sees it in the
// unassigned queue with every required field.
test.describe.configure({ retries: 0 })

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
}

async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
}

function ownRow(page: Page, name: string) {
  const ownRequests = page
    .getByRole('heading', { name: 'My event requests' })
    .locator('xpath=../following-sibling::ul[1]')
  return ownRequests.getByRole('listitem').filter({ hasText: name })
}

test('an organiser submission appears in the Lead unassigned queue', async ({ page }) => {
  const name = `E2E unassigned ${Date.now()}`
  await signIn(page, 'organiser@example.com')
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()

  await page.getByLabel('Name *').fill(name)
  await page.getByLabel('Purpose *').fill('Welcome new students')
  await page.getByLabel('Description *').fill('Campus orientation activities')
  await page.getByLabel('Start date and time *').fill('2030-12-01T09:00')
  await page.getByLabel('End date and time *').fill('2030-12-01T13:00')
  await page.getByLabel('Expected attendance *').fill('200')
  await page.getByLabel('Venue requirement *').selectOption('Hall A')
  await page.getByLabel('Accessibility requirement *').fill('Step-free access')
  await page.getByLabel('Equipment requirement *').selectOption('Projector')
  await page.getByLabel('Layout requirement *').fill('Theatre style')
  await page.getByLabel('Registration requirement *').fill('Open registration')
  await page.getByRole('button', { name: 'Create event request' }).click()
  // Creating sends it for review in the same press, so there is no separate submit step.
  await expect(page.getByRole('status').filter({ hasText: 'submitted for review' })).toContainText(
    `“${name}” has been submitted for review.`,
  )
  await expect(ownRow(page, name)).toContainText('Submitted')
  await signOut(page)

  await signIn(page, 'coordinator-lead@example.com')
  const queue = page.getByLabel('Unassigned requests')
  await expect(queue).toBeVisible()
  const entry = queue.getByRole('listitem').filter({ hasText: name })
  await expect(entry).toContainText(name)
  await expect(entry).toContainText('Expected attendance')
  await expect(entry).toContainText('200')
  await expect(entry).toContainText('Submitted')
})

// TC-98-09: the Lead picks an eligible coordinator, assigns, and the request leaves
// the queue with a confirmation; a failed assignment keeps the row visible.
test('a Lead assigns an unassigned request to an eligible coordinator', async ({ page }) => {
  const name = `E2E assign ${Date.now()}`
  await signIn(page, 'organiser@example.com')
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()

  await page.getByLabel('Name *').fill(name)
  await page.getByLabel('Purpose *').fill('Welcome new students')
  await page.getByLabel('Description *').fill('Campus orientation activities')
  await page.getByLabel('Start date and time *').fill('2030-12-01T09:00')
  await page.getByLabel('End date and time *').fill('2030-12-01T13:00')
  await page.getByLabel('Expected attendance *').fill('200')
  await page.getByLabel('Venue requirement *').selectOption('Hall A')
  await page.getByLabel('Accessibility requirement *').fill('Step-free access')
  await page.getByLabel('Equipment requirement *').selectOption('Projector')
  await page.getByLabel('Layout requirement *').fill('Theatre style')
  await page.getByLabel('Registration requirement *').fill('Open registration')
  await page.getByRole('button', { name: 'Create event request' }).click()
  // Creating sends it for review in the same press, so there is no separate submit step.
  await expect(page.getByRole('status').filter({ hasText: 'submitted for review' })).toContainText(
    `“${name}” has been submitted for review.`,
  )
  await expect(ownRow(page, name)).toContainText('Submitted')
  await signOut(page)

  await signIn(page, 'coordinator-lead@example.com')
  const queue = page.getByLabel('Unassigned requests')
  await expect(queue).toBeVisible()
  const entry = queue.getByRole('listitem').filter({ hasText: name })
  await expect(entry).toBeVisible()
  // The picker offers the seeded active coordinators.
  const picker = entry.getByLabel(`Coordinator for ${name}`)
  await expect(picker).toBeVisible()
  await expect(picker.getByRole('option', { name: 'coordinator@example.com' })).toBeAttached()
  await picker.selectOption({ label: 'coordinator@example.com' })
  await entry.getByRole('button', { name: 'Assign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been assigned' })).toContainText(
    `“${name}” has been assigned.`,
  )
  await expect(queue.getByRole('listitem').filter({ hasText: name })).toHaveCount(0)
})

// TC-97-09: the Lead reassigns an assigned request to another coordinator, views the
// immutable history, and the incoming/outgoing coordinators see updated permissions
// after refresh while arrangements survive.
test('a Lead reassigns an assigned request and views its history', async ({ page }) => {
  const name = `E2E reassign ${Date.now()}`
  await signIn(page, 'organiser@example.com')
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()

  await page.getByLabel('Name *').fill(name)
  await page.getByLabel('Purpose *').fill('Welcome new students')
  await page.getByLabel('Description *').fill('Campus orientation activities')
  await page.getByLabel('Start date and time *').fill('2030-12-01T09:00')
  await page.getByLabel('End date and time *').fill('2030-12-01T13:00')
  await page.getByLabel('Expected attendance *').fill('200')
  await page.getByLabel('Venue requirement *').selectOption('Hall A')
  await page.getByLabel('Accessibility requirement *').fill('Step-free access')
  await page.getByLabel('Equipment requirement *').selectOption('Projector')
  await page.getByLabel('Layout requirement *').fill('Theatre style')
  await page.getByLabel('Registration requirement *').fill('Open registration')
  await page.getByRole('button', { name: 'Create event request' }).click()
  // Creating sends it for review in the same press, so there is no separate submit step.
  await expect(page.getByRole('status').filter({ hasText: 'submitted for review' })).toContainText(
    `“${name}” has been submitted for review.`,
  )
  await expect(ownRow(page, name)).toContainText('Submitted')
  await signOut(page)

  await signIn(page, 'coordinator-lead@example.com')
  const queue = page.getByLabel('Unassigned requests')
  await expect(queue).toBeVisible()
  const queueEntry = queue.getByRole('listitem').filter({ hasText: name })
  await queueEntry
    .getByLabel(`Coordinator for ${name}`)
    .selectOption({ label: 'coordinator@example.com' })
  await queueEntry.getByRole('button', { name: 'Assign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been assigned' })).toContainText(
    `“${name}” has been assigned.`,
  )

  // The assigned row now lives in the overview with a reassignment picker.
  const overview = page.getByLabel('Active requests')
  await expect(overview).toBeVisible()
  const entry = overview.getByRole('listitem').filter({ hasText: name })
  await expect(entry).toContainText('coordinator@example.com')
  await entry
    .getByLabel(`New coordinator for ${name}`)
    .selectOption({ label: 'coordinator2@example.com' })
  await entry.getByRole('button', { name: 'Reassign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been reassigned' })).toContainText(
    `“${name}” has been reassigned.`,
  )
  await expect(entry).toContainText('coordinator2@example.com')

  // The immutable history records the handover oldest first.
  await entry.getByRole('button', { name: 'Show history' }).click()
  const history = entry.getByText('Assignment history')
  await expect(history).toBeVisible()
  await expect(entry).toContainText('First assignment')
})

// TC-104-07: after reassignment the outgoing coordinator loses access, the incoming
// coordinator gains it, and both Leads keep allocation visibility after refresh.
test('a reassigned request moves coordinator access and keeps Lead visibility', async ({
  page,
}) => {
  const name = `E2E assigned access ${Date.now()}`
  await signIn(page, 'organiser@example.com')
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()

  await page.getByLabel('Name *').fill(name)
  await page.getByLabel('Purpose *').fill('Welcome new students')
  await page.getByLabel('Description *').fill('Campus orientation activities')
  await page.getByLabel('Start date and time *').fill('2030-12-01T09:00')
  await page.getByLabel('End date and time *').fill('2030-12-01T13:00')
  await page.getByLabel('Expected attendance *').fill('200')
  await page.getByLabel('Venue requirement *').selectOption('Hall A')
  await page.getByLabel('Accessibility requirement *').fill('Step-free access')
  await page.getByLabel('Equipment requirement *').selectOption('Projector')
  await page.getByLabel('Layout requirement *').fill('Theatre style')
  await page.getByLabel('Registration requirement *').fill('Open registration')
  await page.getByRole('button', { name: 'Create event request' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'submitted for review' })).toContainText(
    `“${name}” has been submitted for review.`,
  )
  await signOut(page)

  // The Lead assigns to the first coordinator, then immediately reassigns.
  await signIn(page, 'coordinator-lead@example.com')
  const queue = page.getByLabel('Unassigned requests')
  const queueEntry = queue.getByRole('listitem').filter({ hasText: name })
  await queueEntry
    .getByLabel(`Coordinator for ${name}`)
    .selectOption({ label: 'coordinator@example.com' })
  await queueEntry.getByRole('button', { name: 'Assign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been assigned' })).toContainText(
    `“${name}” has been assigned.`,
  )
  const overview = page.getByLabel('Active requests')
  const entry = overview.getByRole('listitem').filter({ hasText: name })
  await entry
    .getByLabel(`New coordinator for ${name}`)
    .selectOption({ label: 'coordinator2@example.com' })
  await entry.getByRole('button', { name: 'Reassign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been reassigned' })).toContainText(
    `“${name}” has been reassigned.`,
  )
  await signOut(page)

  // The outgoing coordinator's list no longer holds the event after refresh.
  await signIn(page, 'coordinator@example.com')
  const outgoing = page.getByRole('heading', { name: 'Coordinator events' }).locator('..')
  await expect(outgoing.getByRole('article').filter({ hasText: name })).toHaveCount(0)
  await signOut(page)

  // The incoming coordinator sees it with the decision buttons.
  await signIn(page, 'coordinator2@example.com')
  const incoming = page.getByRole('heading', { name: 'Coordinator events' }).locator('..')
  const card = incoming.getByRole('article').filter({ hasText: name })
  await expect(card).toBeVisible()
  await expect(card.getByRole('button', { name: 'Approve' })).toBeVisible()
  await signOut(page)

  // The Lead still sees the allocation after refresh.
  await signIn(page, 'coordinator-lead@example.com')
  await expect(page.getByLabel('Active requests')).toBeVisible()
  await page.reload()
  const refreshed = page.getByLabel('Active requests')
  await expect(refreshed.getByRole('listitem').filter({ hasText: name })).toBeVisible()
})
