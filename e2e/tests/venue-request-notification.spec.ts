import { expect, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// TC-49-05: the assigned Coordinator submits a new venue request through the booking
// API, then Venue Staff sign in and see one unread notification naming the new-request
// action for the submitted event.
//
// The Pending booking is set up exactly as venue-approval-hold.spec.ts does it: the
// spec's own Approved event on its own day, so the request is conflict-free on a
// reseeded database and on a local one that keeps earlier runs' holds alike.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

const VENUE_NAME = 'Hall A'

test('a new venue request notifies the Venue Staff inbox', async ({ page }) => {
  const event = await createApprovedEvent(page.request, {
    name: `E2E venue request notify ${Date.now()}`,
    lane: 1,
  })
  const coordinator = await tokenFor(page.request, VENUE_SPEC_ACCOUNT)
  const headers = { Authorization: `Bearer ${coordinator}`}
  const venues = (await (await page.request.get(`${API}/api/venues`, { headers })).json()) as {
    id: string
    name: string
  }[]
  const venue = venues.find((row) => row.name === VENUE_NAME)
  if (!venue) throw new Error(`Seeded venue ${VENUE_NAME} missing`)
  const created = await page.request.post(`${API}/api/event-requests/${event.id}/venue-bookings`, {
    headers,
    data: {
      venue_id: venue.id,
      session_label: 'Request notify session',
      start_at: event.start_at,
      end_at: event.end_at,
    },
  })
  expect(created.ok(), `booking request -> ${created.status()}`).toBe(true)

  await signIn(page, 'venue-staff@example.com')
  const inbox = page.getByLabel('Notifications')
  await expect(inbox).toBeVisible()
  // The newest notification is the just-submitted request; it is unread and names the
  // new-request action for this spec's event (the inbox shows the event ID).
  const items = inbox.getByRole('listitem')
  await expect(items.first()).toContainText('Unread')
  await expect(items.first()).toContainText('venue_request_submitted')
  await expect(items.first()).toContainText(event.id)
})
