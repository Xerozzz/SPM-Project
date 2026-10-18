import { expect, type Page, test } from '@playwright/test'

// TC-102-08: a Lead assigns then reassigns a request; the incoming coordinator,
// outgoing coordinator and organiser see assignment notifications in their inboxes,
// while an unrelated user sees none.
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

test('assignment and reassignment notify the affected inboxes only', async ({ page }) => {
  const name = `E2E assignment inbox ${Date.now()}`
  // No baselines: every inbox assertion below is scoped to this run's event ID,
  // so parallel specs assigning other requests cannot shift the counts.
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
  await expect(page.getByRole('status').filter({ hasText: 'has been created' })).toContainText(
    `“${name}” has been created.`,
  )
  await ownRow(page, name).getByRole('button', { name: 'Submit for review' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'submitted for review' })).toContainText(
    `“${name}” has been submitted for review.`,
  )
  const eventId = await ownRequestId(page, name)
  expect(eventId).not.toBe('')
  await signOut(page)

  // The Lead assigns to the first coordinator, then reassigns to the second.
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

  const overview = page.getByLabel('Active requests')
  await expect(overview).toBeVisible()
  const entry = overview.getByRole('listitem').filter({ hasText: name })
  await entry
    .getByLabel(`New coordinator for ${name}`)
    .selectOption({ label: 'coordinator2@example.com' })
  await entry.getByRole('button', { name: 'Reassign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been reassigned' })).toContainText(
    `“${name}” has been reassigned.`,
  )
  await signOut(page)

  // The incoming coordinator gains exactly one unread reassignment notification.
  await signIn(page, 'coordinator2@example.com')
  const incomingEntries = inboxEntries(page, 'coordinator_reassigned', eventId)
  await expect(incomingEntries).toHaveCount(1)
  await expect(incomingEntries.first()).toContainText('Unread')
  await signOut(page)

  // The outgoing coordinator gains exactly one unread reassignment notification.
  await signIn(page, 'coordinator@example.com')
  const outgoingEntries = inboxEntries(page, 'coordinator_reassigned', eventId)
  await expect(outgoingEntries).toHaveCount(1)
  await expect(outgoingEntries.first()).toContainText('Unread')
  await signOut(page)

  // The owning organiser gains one assignment and one reassignment notification.
  await signIn(page, 'organiser@example.com')
  const organiserAssigned = inboxEntries(page, 'coordinator_assigned', eventId)
  const organiserReassigned = inboxEntries(page, 'coordinator_reassigned', eventId)
  await expect(organiserAssigned).toHaveCount(1)
  await expect(organiserReassigned).toHaveCount(1)
  await expect(organiserAssigned.first()).toContainText('Unread')
  await expect(organiserReassigned.first()).toContainText('Unread')
  await signOut(page)

  // An unrelated user gains no assignment notification.
  await signIn(page, 'attendee@example.com')
  await expect(inboxEntries(page, 'coordinator_', eventId)).toHaveCount(0)
})
