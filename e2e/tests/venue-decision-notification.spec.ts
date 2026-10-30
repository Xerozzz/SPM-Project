import { expect, type APIRequestContext, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// TC-122-06: Venue Staff approve a Pending venue booking and edit the hold's expiry;
// the assigned Coordinator sees both alerts in their inbox, with a link to the
// authorised coordinator view. An unrelated user is told nothing.
//
// The Pending booking is set up through the real booking API as the coordinator
// assigned to an Approved event this spec creates for itself; the approval and the
// expiry edit go through the API as Venue Staff, which is what stages the alerts.

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

async function call(
  request: APIRequestContext,
  token: string,
  method: 'GET' | 'POST' | 'PATCH',
  path: string,
  data?: unknown,
) {
  const response = await request.fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data,
  })
  expect(response.ok(), `${method} ${path} -> ${response.status()} ${await response.text()}`).toBe(
    true,
  )
  return response.json() as Promise<Record<string, string>>
}

function decisionEntries(page: Page, eventId: string) {
  return page
    .getByLabel('Notifications', { exact: true })
    .getByRole('listitem')
    .filter({ hasText: /venue_booking_approved|venue_hold_expiry_updated/ })
    .filter({ hasText: eventId })
}

test('an approval and an expiry edit each tell the Coordinator, with a link', async ({
  page,
}) => {
  const event = await createApprovedEvent(page.request, {
    name: `E2E venue decision ${Date.now()}`,
    lane: 1,
  })
  const coordinator = await tokenFor(page.request, VENUE_SPEC_ACCOUNT)
  const headers = { Authorization: `Bearer ${coordinator}` }
  const venues = (await (await page.request.get(`${API}/api/venues`, { headers })).json()) as {
    id: string
    name: string
  }[]
  const venue = venues.find((row) => row.name === 'Hall A')
  expect(venue, 'seeded venue Hall A').toBeDefined()
  const created = (await call(page.request, coordinator, 'POST', `/api/event-requests/${event.id}/venue-bookings`, {
    venue_id: venue!.id,
    session_label: 'Decision session',
    start_at: event.start_at,
    end_at: event.end_at,
  })) as { id: string }

  // Venue Staff approve the Pending request, then edit the active hold's expiry.
  const staff = await tokenFor(page.request, 'venue-staff@example.com')
  const firstExpiry = new Date(new Date(event.start_at).getTime() - 2 * 24 * 3_600_000)
  const laterExpiry = new Date(new Date(event.start_at).getTime() - 1 * 24 * 3_600_000)
  await call(page.request, staff, 'POST', `/api/venue-bookings/${created.id}/approve`, {
    expires_at: firstExpiry.toISOString(),
  })
  await call(page.request, staff, 'PATCH', `/api/venue-bookings/${created.id}/hold`, {
    expires_at: laterExpiry.toISOString(),
  })

  // The assigned Coordinator sees both alerts in their inbox, with the view link.
  await signIn(page, VENUE_SPEC_ACCOUNT)
  await page.getByRole('button', { name: /^Notifications/ }).click()
  const entries = decisionEntries(page, event.id)
  await expect(entries).toHaveCount(2)
  await expect(
    entries.first().getByRole('link', { name: 'View venue decision' }),
  ).toHaveAttribute('href', '#coordinator-events')
  await signOut(page)

  // An unrelated user is told nothing.
  await signIn(page, 'attendee@example.com')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(decisionEntries(page, event.id)).toHaveCount(0)
})
