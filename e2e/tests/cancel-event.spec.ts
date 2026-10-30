import { expect, type APIRequestContext, type Page, test } from '@playwright/test'

import { API, createApprovedEvent, tokenFor, VENUE_SPEC_ACCOUNT } from '../support/approved-event'

// SCRUM-115: the Organiser asks for a Confirmed event to be cancelled, the assigned
// Coordinator applies the request on screen, and the people who worked on the event are
// told: venue staff who held it, technical support who reserved its equipment and the
// Safety Officer who approved it. An unrelated user is told nothing.
//
// VENUE_SPEC_ACCOUNT is both the Organiser and the Coordinator of events made here, so
// both halves of the request are driven from one sign-in.
//
// It books a venue it creates for itself, so it never competes with the venue specs.

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

/** A Confirmed event: venue held then booked, equipment reserved, safety approved. */
async function confirmedEvent(request: APIRequestContext) {
  const stamp = Date.now()
  const event = await createApprovedEvent(request, { name: `E2E cancel ${stamp}`, lane: 2 })
  const staff = await tokenFor(request, 'venue-staff@example.com')
  const venue = await call(request, staff, 'POST', '/api/venues', {
    name: `E2E Cancel Hall ${stamp}`,
    location: 'E2E cancel spec',
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
  const officer = await tokenFor(request, 'safety-officer@example.com')
  const plan = await call(request, officer, 'GET', `/api/safety-reviews/${event.id}`)
  await call(request, officer, 'POST', `/api/safety-reviews/${event.id}`, {
    decision: 'approve',
    comment: 'Egress and capacity check out.',
    plan_fingerprint: plan.plan_fingerprint,
  })
  await call(request, coordinator, 'POST', `/api/event-requests/${event.id}/confirm`)
  return event
}

function inboxEntries(page: Page, type: string, eventId: string) {
  return page
    .getByLabel('Notifications', { exact: true })
    .getByRole('listitem')
    .filter({ hasText: type })
    .filter({ hasText: eventId })
}

test('a requested cancellation is applied and the staff who took part are told', async ({
  page,
}) => {
  const event = await confirmedEvent(page.request)

  await signIn(page, VENUE_SPEC_ACCOUNT)

  // AC1: the Organiser asks, with a reason.
  await page.getByRole('button', { name: 'My Events' }).click()
  const row = page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name: event.name, exact: true }) })
  await row.getByRole('button', { name: `View details for ${event.name}` }).click()
  await row.getByRole('button', { name: 'Ask to cancel', exact: true }).click()
  await page.getByLabel('Why should it be cancelled?').fill('Speaker is ill')
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByText('Your Coordinator has not answered yet.')).toBeVisible()

  // AC1 to AC3: the Coordinator sees the request and applies it.
  await page.getByRole('button', { name: 'Review Queue' }).click()
  const card = page
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name: event.name, exact: true }) })
  await card.getByRole('button', { name: `View details for ${event.name}` }).click()
  await card.getByRole('button', { name: 'Cancel this event…', exact: true }).click()
  const panel = card
    .getByRole('heading', { name: 'Cancel this event', exact: true })
    .locator('xpath=..')
  await expect(panel.getByText('Speaker is ill')).toBeVisible()
  await panel.getByRole('button', { name: 'Cancel the event as asked' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'is cancelled' })).toContainText(
    event.name,
  )

  // AC3: the Organiser's list shows it Cancelled, with the reason.
  await page.reload()
  await page.getByRole('button', { name: 'My Events' }).click()
  await expect(row.getByText('Cancelled', { exact: true })).toBeVisible()
  await expect(row.getByText(/Reason: Speaker is ill/)).toBeVisible()
  await signOut(page)

  // AC9: each member of staff who worked on the event has one cancellation notice.
  for (const email of [
    'venue-staff@example.com',
    'tech-support@example.com',
    'safety-officer@example.com',
  ]) {
    await signIn(page, email)
    await page.getByRole('button', { name: /^Notifications/ }).click()
    await expect(inboxEntries(page, 'event_cancelled', event.id)).toHaveCount(1)
    await signOut(page)
  }

  // An unrelated user is told nothing.
  await signIn(page, 'attendee@example.com')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(inboxEntries(page, 'event_cancelled', event.id)).toHaveCount(0)
})

test('each attendee whose registration was cancelled is told, and nobody else', async ({
  page,
}) => {
  // SCRUM-135: an attendee registers, the Coordinator cancels, and the attendee's inbox
  // shows the cancellation. Someone who never registered is told nothing.
  const event = await confirmedEvent(page.request)
  const owner = await tokenFor(page.request, VENUE_SPEC_ACCOUNT)
  await call(page.request, owner, 'POST', `/api/event-requests/${event.id}/registration/open`, {})
  const attendee = await tokenFor(page.request, 'attendee@example.com')
  await call(page.request, attendee, 'POST', `/api/attendee/events/${event.id}/registrations`, {
    full_name: 'Ada Lovelace',
    age: 24,
    phone_number: '+65 8123 4567',
  })
  await call(page.request, owner, 'POST', `/api/event-requests/${event.id}/cancel`, {
    reason: 'Storm warning',
  })

  await signIn(page, 'attendee@example.com')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(inboxEntries(page, 'event_cancelled', event.id)).toHaveCount(1)
  await signOut(page)

  await signIn(page, 'attendee2@example.com')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(inboxEntries(page, 'event_cancelled', event.id)).toHaveCount(0)
})
