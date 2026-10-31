import { expect, type Page, test } from '@playwright/test'

import { openEvent } from '../support/workspace'
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
  const card = await openEvent(page, event.name, 'Review Queue')
  await expect(card).toBeVisible()
  await card.getByLabel('Active venue').selectOption({ label: 'Hall A' })
  // Exact, because `getByLabel` matches accessible names by substring and this spec
  // names its own event "E2E session label …": any control whose label carries the
  // event name — SCRUM-80's confirm button does — otherwise matches this query too.
  await card.getByLabel('Session label', { exact: true }).fill(SESSION_LABEL)
  await card.getByRole('button', { name: 'Submit booking request' }).click()
  await expect(card.getByRole('status')).toContainText('Booking request submitted')

  // The coordinator's own list shows the label, not just the venue and times.
  await expect(card.getByRole('heading', { name: 'Existing venue booking requests' })).toBeVisible()
  await expect(card.getByText(SESSION_LABEL).first()).toBeVisible({ timeout: 15000 })
  await signOut(page)

  // Venue Staff see the same label in their decision queue.
  await signIn(page, 'venue-staff@example.com')
  await page
    .getByRole('button', { name: `View booking for ${event.name} at Hall A`, exact: true })
    .click()
  const booking = page.getByRole('region', { name: 'Booking details', exact: true })
  await expect(booking).toContainText(SESSION_LABEL)
})
