import { expect, type Locator, type Page, test } from '@playwright/test'

// SCRUM-105: the owning Organiser and the current assigned Coordinator open the event's
// assignment history from their own views; reassignment moves the Coordinator's access,
// and neither view offers assign or reassign. The Lead's own history view keeps working
// and now names people by email.
test.describe.configure({ retries: 0 })

const FIRST_ENTRY = 'First assignment → coordinator@example.com by coordinator-lead@example.com'
const SECOND_ENTRY =
  'coordinator@example.com → coordinator2@example.com by coordinator-lead@example.com'
// An ISO 8601 date-time such as 2030-12-01T01:00:00Z: what the API sends, never what
// the viewer should read (AGENTS.md §3: local time only in the UI).
const RAW_ISO = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/

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
  return page
    .getByRole('heading', { name: 'My event requests' })
    .locator('xpath=../following-sibling::ul[1]')
    .getByRole('listitem')
    .filter({ hasText: name })
}

function coordinatorCard(page: Page, name: string) {
  return page
    .getByRole('heading', { name: 'Coordinator events' })
    .locator('..')
    .getByRole('article')
    .filter({ hasText: name })
}

function leadRow(page: Page, name: string) {
  return page.getByLabel('Active requests').getByRole('listitem').filter({ hasText: name })
}

/** The Organiser creates a complete request, which submits it in the same press. */
async function submitAsOrganiser(page: Page, name: string) {
  await signIn(page, 'organiser@example.com')
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
  await expect(ownRow(page, name)).toContainText('Submitted')
}

/** The Lead assigns the request to coordinator@example.com from the unassigned queue. */
async function assignAsLead(page: Page, name: string) {
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
}

/** Opens the toggle and returns the history's entries; the history loads only now. */
async function openHistory(scope: Locator) {
  await scope.getByRole('button', { name: 'View assignment history' }).click()
  await expect(scope.getByText('Assignment history', { exact: true })).toBeVisible()
  return scope.locator('ol').getByRole('listitem')
}

async function expectNoAllocationControls(scope: Locator) {
  await expect(scope.getByRole('button', { name: /^(re)?assign$/i })).toHaveCount(0)
}

/** The time is shown in the viewer's locale; the ISO value stays only in `dateTime`. */
async function expectLocalTime(entry: Locator) {
  const time = entry.locator('time')
  await expect(time).toHaveAttribute('datetime', RAW_ISO)
  await expect(time).not.toHaveText(RAW_ISO)
  await expect(entry).not.toContainText(RAW_ISO)
  const iso = await time.getAttribute('datetime')
  expect(await time.textContent()).not.toBe(iso)
}

test('owner and current coordinator view assignment history; reassignment moves access', async ({
  page,
}) => {
  const name = `E2E history access ${Date.now()}`

  // Before any assignment the history shows its empty state.
  await submitAsOrganiser(page, name)
  await openHistory(ownRow(page, name))
  await expect(ownRow(page, name)).toContainText(`No assignment history for ${name} yet.`)
  await signOut(page)

  await assignAsLead(page, name)
  await signOut(page)

  // The owning Organiser sees the first entry in local time, with no allocation
  // controls, and hiding the history removes the entries again.
  await signIn(page, 'organiser@example.com')
  const ownerEntries = await openHistory(ownRow(page, name))
  await expect(ownerEntries).toHaveCount(1)
  await expect(ownerEntries.first()).toContainText(FIRST_ENTRY)
  await expectLocalTime(ownerEntries.first())
  await expectNoAllocationControls(ownRow(page, name))
  await ownRow(page, name).getByRole('button', { name: 'Hide assignment history' }).click()
  await expect(ownerEntries).toHaveCount(0)
  await expect(ownRow(page, name).getByText('Assignment history', { exact: true })).toHaveCount(0)
  await expect(
    ownRow(page, name).getByRole('button', { name: 'View assignment history' }),
  ).toBeVisible()
  await signOut(page)

  // The assigned coordinator sees the same entry on their review card.
  await signIn(page, 'coordinator@example.com')
  const outgoingEntries = await openHistory(coordinatorCard(page, name))
  await expect(outgoingEntries).toHaveCount(1)
  await expect(outgoingEntries.first()).toContainText(FIRST_ENTRY)
  await expectLocalTime(outgoingEntries.first())
  await expectNoAllocationControls(coordinatorCard(page, name))
  await signOut(page)

  // The Lead reassigns to the second coordinator.
  await signIn(page, 'coordinator-lead@example.com')
  await leadRow(page, name)
    .getByLabel(`New coordinator for ${name}`)
    .selectOption({ label: 'coordinator2@example.com' })
  await leadRow(page, name).getByRole('button', { name: 'Reassign' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'has been reassigned' })).toContainText(
    `“${name}” has been reassigned.`,
  )
  await signOut(page)

  // The outgoing coordinator no longer has the card, so no way to the history.
  await signIn(page, 'coordinator@example.com')
  await expect(page.getByRole('heading', { name: 'Coordinator events' })).toBeVisible()
  await expect(coordinatorCard(page, name)).toHaveCount(0)
  await signOut(page)

  // The incoming coordinator, and the owner, see both entries oldest first.
  for (const [email, scope] of [
    ['coordinator2@example.com', coordinatorCard],
    ['organiser@example.com', ownRow],
  ] as const) {
    await signIn(page, email)
    const entries = await openHistory(scope(page, name))
    await expect(entries).toHaveCount(2)
    await expect(entries.nth(0)).toContainText(FIRST_ENTRY)
    await expect(entries.nth(1)).toContainText(SECOND_ENTRY)
    await expectLocalTime(entries.nth(1))
    await expectNoAllocationControls(scope(page, name))
    await signOut(page)
  }
})

test('a draft row offers no assignment history toggle', async ({ page }) => {
  const draftName = `E2E history draft ${Date.now()}`
  const submittedName = `E2E history submitted ${Date.now()}`

  // A submitted row in the same list shows the toggle is present where it should be.
  await submitAsOrganiser(page, submittedName)
  await page.reload()
  await page.getByLabel('Name *').fill(draftName)
  await page.getByRole('button', { name: 'Save draft' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'saved as a draft' })).toContainText(
    `“${draftName}” has been saved as a draft.`,
  )

  await expect(ownRow(page, draftName)).toContainText('Draft')
  await expect(
    ownRow(page, draftName).getByRole('button', { name: 'View assignment history' }),
  ).toHaveCount(0)
  await expect(
    ownRow(page, submittedName).getByRole('button', { name: 'View assignment history' }),
  ).toBeVisible()
})

test("the Lead's active assignments still show the history, now with emails", async ({
  page,
}) => {
  const name = `E2E history lead ${Date.now()}`
  await submitAsOrganiser(page, name)
  await signOut(page)

  await assignAsLead(page, name)
  const row = leadRow(page, name)
  await row.getByRole('button', { name: 'Show history' }).click()
  await expect(row.getByText('Assignment history', { exact: true })).toBeVisible()
  const entries = row.locator('ol').getByRole('listitem')
  await expect(entries).toHaveCount(1)
  await expect(entries.first()).toContainText(FIRST_ENTRY)
  await expectLocalTime(entries.first())
})
