import { expect, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// TC-127-05: the Coordinator submits a revised (replacement) venue request through the
// controlled SCRUM-116 flow — approve a hold, record a closure over it, request a
// replacement at another venue — then Venue Staff sign in and see one unread
// notification naming the revision action for the revised event, with a link to the
// authorised staff view.
//
// The event uses its own lane/day so the bookings are conflict-free on a reseeded
// database and on a local one that keeps earlier runs' holds alike.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

const VENUE_NAME = 'Hall A'
const OTHER_VENUE = 'SCIS Seminar Room 2-1'

test('a revised venue request notifies the Venue Staff inbox', async ({ page }) => {
  const event = await createApprovedEvent(page.request, {
    name: `E2E revision notify ${Date.now()}`,
    lane: 0,
  })
  const coordinator = await tokenFor(page.request, VENUE_SPEC_ACCOUNT)
  const headers = { Authorization: `Bearer ${coordinator}` }
  const venues = (await (
    await page.request.get(`${API}/api/venues`, { headers })
  ).json()) as {
    id: string
    name: string
  }[]
  const venue = venues.find((row) => row.name === VENUE_NAME)
  const other = venues.find((row) => row.name === OTHER_VENUE)
  if (!venue || !other) throw new Error('Seeded venues missing')
  const created = await page.request.post(`${API}/api/event-requests/${event.id}/venue-bookings`, {
    headers,
    data: {
      venue_id: venue.id,
      session_label: 'Revision notify session',
      start_at: event.start_at,
      end_at: event.end_at,
    },
  })
  expect(created.ok(), `booking request -> ${created.status()}`).toBe(true)
  const booking = (await created.json()) as { id: string }

  // Approve the request into a live hold so a closure can affect it.
  const staffToken = await tokenFor(page.request, 'venue-staff@example.com')
  const staffHeaders = { Authorization: `Bearer ${staffToken}` }
  const expires = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString()
  const approved = await page.request.post(`${API}/api/venue-bookings/${booking.id}/approve`, {
    headers: staffHeaders,
    data: { expires_at: expires },
  })
  expect(approved.ok(), `booking approve -> ${approved.status()}`).toBe(true)

  // Record a closure over the hold so the arrangement needs a replacement.
  const start = new Date(event.start_at)
  const closed = await page.request.post(`${API}/api/venues/${venue.id}/unavailabilities`, {
    headers: staffHeaders,
    data: {
      starts_at: start.toISOString(),
      ends_at: new Date(start.getTime() + 3600_000).toISOString(),
      reason: 'Revision notify maintenance',
    },
  })
  expect(closed.ok(), `closure record -> ${closed.status()}`).toBe(true)

  // Submit the revised (replacement) request at another venue.
  const revised = await page.request.post(`${API}/api/event-requests/${event.id}/venue-bookings`, {
    headers,
    data: {
      venue_id: other.id,
      session_label: 'Revision notify session',
      start_at: event.start_at,
      end_at: event.end_at,
      replaces_booking_id: booking.id,
    },
  })
  expect(revised.ok(), `revision request -> ${revised.status()}`).toBe(true)

  // Clean up the closure so later runs and specs see a free venue.
  const closures = (await (
    await page.request.get(`${API}/api/venues/${venue.id}/unavailabilities`, {
      headers: staffHeaders,
    })
  ).json()) as { id: string }[]
  for (const closure of closures) {
    await page.request.delete(`${API}/api/venues/${venue.id}/unavailabilities/${closure.id}`, {
      headers: staffHeaders,
    })
  }

  await signIn(page, 'venue-staff@example.com')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  const inbox = page.getByLabel('Notifications', { exact: true })
  await expect(inbox).toBeVisible()
  // Parallel specs submit venue requests too, so the newest item may belong to another
  // event. Select this spec's own: the label names the event ID after the read state,
  // which is left out of the match so that "Unread" is still asserted below.
  const own = inbox
    .getByRole('listitem', { name: new RegExp(`notification for event ${event.id}$`) })
    .filter({ hasText: 'venue_revision_submitted' })
  await expect(own).toHaveCount(1)
  await expect(own).toContainText('Unread')
  await expect(own).toContainText('venue_revision_submitted')
  await expect(own).toContainText(event.id)
  await expect(own.getByRole('link', { name: 'Review revised venue request' })).toHaveAttribute(
    'href',
    '#venue-booking-decisions',
  )
})
