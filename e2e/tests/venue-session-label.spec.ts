import { expect, type Page, test } from '@playwright/test'

// SCRUM-111 TC-111-11: a coordinator books one labelled session of a multi-session
// event through the UI, and the label plus the session period (not the parent event
// period) show on the request, in the staff queue, and on the calendar.
//
// The seeded "Careers Fair" event is the multi-session parent; the session is a
// two-hour slice of it. CI reseeds before every run, so the venue starts free.

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

const SESSION_LABEL = 'E2E morning workshop'

test('a labelled session request shows its label and period everywhere', async ({ page }) => {
  await signIn(page, 'coordinator@example.com')

  // Find the seeded Approved event and open its booking card.
  const card = page
    .getByRole('article')
    .filter({ hasText: 'Careers Fair' })
    .first()
  await expect(card).toBeVisible()
  await card.getByLabel('Active venue').selectOption({ label: 'Hall A' })
  await card.getByLabel('Session label').fill(SESSION_LABEL)
  await card.getByRole('button', { name: 'Submit booking request' }).click()
  await expect(card.getByRole('status')).toContainText('Booking request submitted')

  // The coordinator's own list shows the label, not just the venue and times.
  const existing = page.getByRole('heading', { name: 'Existing venue booking requests' })
  await expect(existing).toBeVisible()
  await expect(page.getByRole('listitem').filter({ hasText: SESSION_LABEL })).toBeVisible()
  await signOut(page)

  // Venue Staff see the same label in their decision queue.
  await signIn(page, 'venue-staff@example.com')
  const queue = page.locator('main section', {
    has: page.getByRole('heading', { name: 'Venue booking requests' }),
  })
  await expect(
    queue.getByRole('article').filter({ hasText: SESSION_LABEL }).first(),
  ).toBeVisible()
})
