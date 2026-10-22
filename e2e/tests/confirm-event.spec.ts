import { expect, type APIRequestContext, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-80: the assigned Coordinator confirms an event once its arrangements and the
// Safety Officer's approval are in order.
//
// This is the only automated proof of the whole chain the customer described — venue
// held, equipment reserved, safety approved, then and only then Confirmed — so it drives
// the real screen rather than the API, and checks the two states that matter: refused
// with a reason, and committed with its holds.
//
// It books a venue it creates for itself, so it never competes with the venue specs for
// a slot however often it re-runs.

async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
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

/** An arranged event: its venue held and its equipment assessed and reserved. */
async function arrangedEvent(request: APIRequestContext, label: string) {
  const stamp = Date.now()
  const event = await createApprovedEvent(request, { name: `${label} ${stamp}`, lane: 2 })
  const staff = await tokenFor(request, 'venue-staff@example.com')
  const venue = await call(request, staff, 'POST', '/api/venues', {
    name: `E2E Confirm Hall ${label} ${stamp}`,
    location: 'E2E confirm spec',
    maximum_capacity: 200,
    facilities: ['Projector'],
    supported_layouts: ['theatre'],
    accessibility_features: ['Step-free access'],
    opens_at: '00:00:00',
    closes_at: '23:59:00',
    setup_minutes: 0,
    turnaround_minutes: 0,
  })

  const coordinator = await tokenFor(request, VENUE_SPEC_ACCOUNT)
  const booking = await call(
    request,
    coordinator,
    'POST',
    `/api/event-requests/${event.id}/venue-bookings`,
    {
      venue_id: venue.id,
      session_label: 'Main session',
      start_at: event.start_at,
      end_at: event.end_at,
    },
  )
  // SCRUM-83: a hold may not outlast the event start, so it expires an hour before.
  await call(request, staff, 'POST', `/api/venue-bookings/${booking.id}/hold`, {
    expires_at: new Date(Date.parse(event.start_at) - 3_600_000).toISOString(),
  })

  const requirements = (await call(
    request,
    coordinator,
    'GET',
    `/api/event-requests/${event.id}/equipment-requirements`,
  )) as unknown as { id: string }[]
  const tech = await tokenFor(request, 'tech-support@example.com')
  await call(request, tech, 'PATCH', `/api/equipment-requirements/${requirements[0].id}/review`, {
    review_status: 'available',
  })
  await call(
    request,
    tech,
    'POST',
    `/api/event-requests/${event.id}/equipment-requirements/${requirements[0].id}/reserve`,
    {},
  )
  return { event, bookingId: booking.id }
}

/** The Safety Officer approves the plan exactly as it stands (SCRUM-79, ADR-0048). */
async function approveSafety(request: APIRequestContext, eventId: string) {
  const officer = await tokenFor(request, 'safety-officer@example.com')
  const plan = await call(request, officer, 'GET', `/api/safety-reviews/${eventId}`)
  await call(request, officer, 'POST', `/api/safety-reviews/${eventId}`, {
    decision: 'approve',
    comment: 'Egress and capacity check out.',
    plan_fingerprint: plan.plan_fingerprint,
  })
}

test('an arranged event cannot be confirmed until safety has approved it', async ({ page }) => {
  // AC2, and the customer's answer in Customer Clarification 3: safety approval is a
  // precondition for confirmation, not a formality alongside it.
  const { event } = await arrangedEvent(page.request, 'E2E confirm blocked')

  await signIn(page, VENUE_SPEC_ACCOUNT)
  // Anchored on the button, whose label names this event, rather than on the card: the
  // Coordinator's cards contain nested articles and the board holds every other event
  // this account has, so "the article mentioning the name" is not one element.
  const button = page.getByRole('button', { name: `Confirm ${event.name}` })
  await expect(button).toBeVisible({ timeout: 15000 })
  // The nearest enclosing section, not `filter({has})`: sections nest here, so that
  // would match every ancestor of the button as well as its own panel.
  const panel = button.locator('xpath=ancestor::section[1]')

  await expect(panel.getByText('Not ready to confirm.')).toBeVisible()
  await expect(panel.getByText(/Safety Officer has not reviewed/)).toBeVisible()
  await expect(button).toBeDisabled()
})

test('a safety-approved event is confirmed and its hold becomes a booking', async ({ page }) => {
  // AC4: the whole chain the customer described, ending in a committed booking.
  const { event, bookingId } = await arrangedEvent(page.request, 'E2E confirm ready')
  await approveSafety(page.request, event.id)

  await signIn(page, VENUE_SPEC_ACCOUNT)
  const button = page.getByRole('button', { name: `Confirm ${event.name}` })
  await expect(button).toBeVisible({ timeout: 15000 })
  await expect(button).toBeEnabled()
  await button.click()

  // Reported by the section rather than the card: a confirmed event leaves the
  // Coordinator's list, so the card it was pressed on is gone by now.
  await expect(page.getByRole('status').filter({ hasText: 'is confirmed' })).toContainText(
    'venue booking is now committed',
  )

  // The banner's wording comes from the `confirmed_bookings` the API returned, so it is
  // evidence that a hold really was converted rather than that a button was pressed.
  // Re-reading the row here is not possible: the Coordinator's access to an event's
  // bookings is pinned to planning, so it is 403 the moment the event is Confirmed.
  // The database-level conversion is proven in tests/integration/test_event_confirmation.
  await expect(page.getByRole('status').filter({ hasText: 'is confirmed' })).toContainText(
    event.name,
  )
  expect(bookingId).toBeTruthy()
})
