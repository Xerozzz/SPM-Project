import { expect, type Page, test } from '@playwright/test'

import { notificationEntries, openWorkspace } from '../support/workspace'
import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// TC-123-05: the Coordinator cancels one venue arrangement through the booking API,
// then Venue Staff sign in and see one unread notification naming the cancellation
// action for the cancelled event, with a link to the authorised staff view.
//
// The booking is set up exactly as venue-request-notification.spec.ts does it: the
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

test('a cancelled venue arrangement notifies the Venue Staff inbox', async ({ page }) => {
  const event = await createApprovedEvent(page.request, {
    name: `E2E arrangement cancel notify ${Date.now()}`,
    lane: 2,
  })
  const coordinator = await tokenFor(page.request, VENUE_SPEC_ACCOUNT)
  const headers = { Authorization: `Bearer ${coordinator}` }
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
      session_label: 'Cancel notify session',
      start_at: event.start_at,
      end_at: event.end_at,
    },
  })
  expect(created.ok(), `booking request -> ${created.status()}`).toBe(true)
  const booking = (await created.json()) as { id: string }

  const cancelled = await page.request.post(
    `${API}/api/event-requests/${event.id}/venue-bookings/${booking.id}/cancel`,
    { headers, data: { reason: 'Room no longer needed' } },
  )
  expect(cancelled.ok(), `booking cancel -> ${cancelled.status()}`).toBe(true)

  await signIn(page, 'venue-staff@example.com')
  await openWorkspace(page, 'Notifications')
  const own = notificationEntries(page, 'venue_arrangement_cancelled', event.id)
  await expect(own).toHaveCount(1)
  await expect(
    own.getByRole('heading', { name: 'Venue arrangement cancelled', exact: true }),
  ).toBeVisible()
  await expect(own).toContainText(event.name)
  await expect(own).toContainText('Unread')
  await own.getByText('Record details', { exact: true }).click()
  await expect(own).toContainText('venue_arrangement_cancelled')
  await expect(own).toContainText(event.id)
  await expect(own.getByRole('link', { name: 'View venue booking decisions' })).toHaveAttribute(
    'href',
    `?view=booking-decisions&booking=${booking.id}`,
  )
})
