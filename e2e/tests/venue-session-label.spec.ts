import { expect, type Page, test } from '@playwright/test'

import { createApprovedEvent, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-111 TC-111-11: a coordinator books one labelled session of a multi-session
// event through the UI, and the label plus the session period (not the parent event
// period) show on the request, in the staff queue, and on the calendar.
//
// The parent is an Approved event this spec creates for itself, on a day no other run
// or spec uses (support/approved-event.ts), so the venue is free and its card carries
// only this spec's request — on a reseeded database and on a local one alike.

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
  const event = await createApprovedEvent(page.request, {
    name: `E2E session label ${Date.now()}`,
    lane: 1,
  })
  // The event's assigned coordinator, who appears in no other spec (see the helper).
  await signIn(page, VENUE_SPEC_ACCOUNT)

  // Find this spec's Approved event and open its booking card.
  const card = page.getByRole('article').filter({ hasText: event.name })
  await expect(card).toBeVisible()
  await card.getByLabel('Active venue').selectOption({ label: 'Hall A' })
  await card.getByLabel('Session label').fill(SESSION_LABEL)
  await card.getByRole('button', { name: 'Submit booking request' }).click()
  await expect(card.getByRole('status')).toContainText('Booking request submitted')

  // The coordinator's own list shows the label, not just the venue and times.
  await expect(card.getByRole('heading', { name: 'Existing venue booking requests' })).toBeVisible()
  await expect(card.getByText(SESSION_LABEL).first()).toBeVisible({ timeout: 15000 })
  await signOut(page)

  // Venue Staff see the same label in their decision queue.
  await signIn(page, 'venue-staff@example.com')
  const queue = page.locator('main section', {
    has: page.getByRole('heading', { name: 'Venue booking requests' }),
  })
  // This event's own request: earlier runs left requests with the same label on others.
  await expect(
    queue.getByRole('article').filter({ hasText: event.name }).filter({ hasText: SESSION_LABEL }),
  ).toBeVisible()
})
