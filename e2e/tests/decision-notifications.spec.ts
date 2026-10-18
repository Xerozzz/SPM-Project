import { expect, type Page, test } from '@playwright/test'

// TC-94-09: an organiser creates a request, the Lead assigns it, the coordinator
// approves it, and the organiser's inbox gains one unread approval notification
// naming the event — while an unrelated user sees none.

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

function inboxEntries(page: Page, type: string, eventId: string) {
  return page
    .getByLabel('Notifications')
    .getByRole('listitem')
    .filter({ hasText: type })
    .filter({ hasText: eventId })
}

async function ownRequestId(page: Page, name: string) {
  return page.evaluate(async (requestName) => {
    const raw = localStorage.getItem('connectsphere.token')
    const token = raw ? (JSON.parse(raw) as { token: string }).token : ''
    const response = await fetch('/api/event-requests', {
      headers: { Authorization: `Bearer ${token}` },
    })
    const rows = (await response.json()) as { id: string; name: string | null }[]
    return rows.find((row) => row.name === requestName)?.id ?? ''
  }, name)
}

test('an approved request notifies the owning organiser inbox', async ({ page }) => {
  const name = `E2E decision inbox ${Date.now()}`
  // Every inbox assertion below is scoped to this run's event ID, so parallel
  // specs deciding other requests cannot shift the counts.
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
  const eventId = await ownRequestId(page, name)
  expect(eventId).not.toBe('')
  await signOut(page)

  // The Lead assigns the request to the first coordinator.
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
  await signOut(page)

  // The assigned coordinator approves the request.
  await signIn(page, 'coordinator@example.com')
  const review = page.getByRole('heading', { name: 'Coordinator events' }).locator('..')
  const card = review.getByRole('article').filter({ hasText: name })
  await expect(card).toBeVisible()
  await card.getByRole('button', { name: 'Approve' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been approved' })).toContainText(
    `“${name}” has been approved.`,
  )
  await signOut(page)

  // The owning organiser gains exactly one unread approval notification.
  await signIn(page, 'organiser@example.com')
  const entries = inboxEntries(page, 'request_approved', eventId)
  await expect(entries).toHaveCount(1)
  await expect(entries.first()).toContainText('Unread')
  await signOut(page)

  // An unrelated user gains no decision notification.
  await signIn(page, 'attendee@example.com')
  await expect(inboxEntries(page, 'request_', eventId)).toHaveCount(0)
})
