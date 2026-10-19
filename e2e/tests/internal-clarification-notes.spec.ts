import { expect, type Page, test } from '@playwright/test'

// TC-106-09: the assigned Coordinator records an internal note and sees it after
// reload; the Organiser has no clarification surface; after a Lead reassigns, the
// outgoing Coordinator loses the note and the incoming Coordinator gains it.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
}

async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
}

async function createSubmittedRequest(page: Page, name: string) {
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
}

function coordinatorCard(page: Page, name: string) {
  const section = page.getByRole('heading', { name: 'Coordinator events' }).locator('..')
  return section.getByRole('article').filter({ hasText: name })
}

test('internal notes stay with the current assignee, never the organiser', async ({ page }) => {
  const name = `E2E internal notes ${Date.now()}`
  const note = `Offline call ${Date.now()}: venue confirmed layout TBC`

  await signIn(page, 'organiser@example.com')
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()
  await createSubmittedRequest(page, name)
  await signOut(page)

  await signIn(page, 'coordinator-lead@example.com')
  const queueEntry = page
    .getByLabel('Unassigned requests')
    .getByRole('listitem')
    .filter({ hasText: name })
  await queueEntry
    .getByLabel(`Coordinator for ${name}`)
    .selectOption({ label: 'coordinator@example.com' })
  await queueEntry.getByRole('button', { name: 'Assign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been assigned' })).toContainText(
    `“${name}” has been assigned.`,
  )
  await signOut(page)

  // The assigned Coordinator records an internal note and still sees it after reload.
  await signIn(page, 'coordinator@example.com')
  const card = coordinatorCard(page, name)
  await expect(card).toBeVisible()
  await expect(card.getByText('Internal clarification notes')).toBeVisible()
  await card.getByLabel('Internal note').fill(note)
  await card.getByRole('button', { name: 'Record internal note' }).click()
  await expect(card.getByRole('status').filter({ hasText: 'Message sent' })).toContainText(
    'Message sent.',
  )
  await page.reload()
  await expect(coordinatorCard(page, name).getByText(note)).toBeVisible()
  await signOut(page)

  // The Organiser has no clarification surface on their own submitted request.
  await signIn(page, 'organiser@example.com')
  await expect(page.getByRole('heading', { name: 'My event requests' })).toBeVisible()
  const ownRequests = page
    .getByRole('heading', { name: 'My event requests' })
    .locator('xpath=../following-sibling::ul[1]')
  const ownRow = ownRequests.getByRole('listitem').filter({ hasText: name })
  await expect(ownRow).toContainText('Submitted')
  await expect(ownRow.getByText('Internal clarification notes')).toHaveCount(0)
  await expect(ownRow.getByText(note)).toHaveCount(0)
  // Exact match: the Organisation calendar renders "View <event name> details"
  // buttons, and this spec's event name contains "internal notes" as a substring.
  // A substring query would false-positive on that button; the real textarea's
  // accessible name is exactly "Internal note".
  await expect(page.getByLabel('Internal note', { exact: true })).toHaveCount(0)
  await signOut(page)

  // The Lead reassigns; the outgoing Coordinator loses the note.
  await signIn(page, 'coordinator-lead@example.com')
  const overviewEntry = page
    .getByLabel('Active requests')
    .getByRole('listitem')
    .filter({ hasText: name })
  await overviewEntry
    .getByLabel(`New coordinator for ${name}`)
    .selectOption({ label: 'coordinator2@example.com' })
  await overviewEntry.getByRole('button', { name: 'Reassign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been reassigned' })).toContainText(
    `“${name}” has been reassigned.`,
  )
  await signOut(page)

  await signIn(page, 'coordinator@example.com')
  const outgoing = page.getByRole('heading', { name: 'Coordinator events' }).locator('..')
  await expect(outgoing.getByRole('article').filter({ hasText: name })).toHaveCount(0)
  await signOut(page)

  // The incoming Coordinator inherits the existing note and can add another.
  await signIn(page, 'coordinator2@example.com')
  const incoming = coordinatorCard(page, name)
  await expect(incoming).toBeVisible()
  await expect(incoming.getByText(note)).toBeVisible()
  const followUp = `Follow-up ${Date.now()}: caterer confirmed`
  await incoming.getByLabel('Internal note').fill(followUp)
  await incoming.getByRole('button', { name: 'Record internal note' }).click()
  await expect(incoming.getByRole('status').filter({ hasText: 'Message sent' })).toContainText(
    'Message sent.',
  )
  await page.reload()
  await expect(coordinatorCard(page, name).getByText(note)).toBeVisible()
  await expect(coordinatorCard(page, name).getByText(followUp)).toBeVisible()
})
